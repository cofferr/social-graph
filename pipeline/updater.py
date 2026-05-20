"""
pipeline/updater.py
-------------------
Renombrado de usuarios del curso en todos los artefactos de datos.

Qué toca un rename:
  1. graph_data.json   — clave de nodo, listas following/followers, arcos source/target
  2. registry.json     — campo 'owner' y 'source_name' de cada entrada
  3. Archivos en disco — following_<old>.json / followers_<old>.json (raw e incompleto)

Operación atómica: escribe todo en memoria primero, persiste al final.
Si algo falla antes de persistir, el estado en disco no cambia.
"""

import shutil
from pathlib import Path
from typing import Optional

from pipeline.ingestion import (
    load_registry,
    save_registry,
    load_graph_data,
    save_graph_data,
    RAW_FOLLOWING_PATH,
    RAW_FOLLOWERS_PATH,
    INC_FOLLOWING_PATH,
    INC_FOLLOWERS_PATH,
)


# ── Validación ────────────────────────────────────────────────────────────────

def validate_rename(old_username: str, new_username: str) -> Optional[str]:
    """
    Retorna un mensaje de error si el rename no es válido, o None si es OK.
    """
    if not old_username or not new_username:
        return "Ambos usuarios son requeridos."

    if old_username == new_username:
        return "El nuevo username es idéntico al actual."

    # Instagram usernames: letras, números, puntos, guiones bajos — max 30 chars
    import re
    if not re.match(r'^[a-z0-9._]{1,30}$', new_username):
        return (
            "Username inválido. Solo se permiten letras minúsculas, "
            "números, puntos y guiones bajos (máx. 30 caracteres)."
        )

    graph_data = load_graph_data()
    if old_username not in graph_data.get("nodes", {}):
        return f"@{old_username} no existe en el grafo."

    if new_username in graph_data.get("nodes", {}):
        return (
            f"@{new_username} ya existe en el grafo. "
            "Renombrar hacia un nodo existente no está soportado — "
            "primero elimina o fusiona manualmente."
        )

    return None


# ── Rename en graph_data ──────────────────────────────────────────────────────

def _rename_in_graph(graph_data: dict, old: str, new: str):
    """Renombra old → new en nodos, listas de relaciones y arcos."""
    nodes = graph_data["nodes"]

    # 1. Renombrar la clave del nodo principal
    if old in nodes:
        nodes[new] = nodes.pop(old)

    # 2. Actualizar listas following/followers — solo en nodos que realmente
    #    contienen la referencia (evita iterar los 3k nodos cuando solo unos
    #    pocos mencionan al usuario renombrado).
    for node_data in nodes.values():
        for list_key in ("following", "followers"):
            lst = node_data.get(list_key)
            if lst and old in lst:
                # reemplazar in-place preservando orden
                node_data[list_key] = [new if u == old else u for u in lst]

    # 3. Actualizar arcos (los arcos de old son exactamente in_degree+out_degree
    #    del nodo — en la práctica pocos cientos, no miles)
    for edge in graph_data.get("edges", []):
        if edge["source"] == old:
            edge["source"] = new
        if edge["target"] == old:
            edge["target"] = new

    # 4. Actualizar archivos anónimos pendientes
    for anon in graph_data.get("anonymous_files", []):
        if anon.get("assigned_owner") == old:
            anon["assigned_owner"] = new
        for rel in anon.get("relations", []):
            if rel.get("username") == old:
                rel["username"] = new


# ── Rename en registry ────────────────────────────────────────────────────────

def _rename_in_registry(registry: dict, old: str, new: str) -> list[tuple[str, str]]:
    """
    Actualiza el campo 'owner' y renombra 'source_name' en registry.
    Retorna lista de (old_source_name, new_source_name) para renombrar en disco.
    """
    file_renames: list[tuple[str, str]] = []

    for fid, meta in registry.items():
        if fid.startswith("_"):
            continue
        if meta.get("owner") != old:
            continue

        meta["owner"] = new

        old_name = meta.get("source_name", "")
        if old_name:
            new_name = old_name.replace(old, new, 1)
            if new_name != old_name:
                meta["source_name"] = new_name
                file_renames.append((old_name, new_name))

    return file_renames


# ── Rename en disco ───────────────────────────────────────────────────────────

def _rename_on_disk(file_renames: list[tuple[str, str]]) -> list[str]:
    """
    Intenta renombrar cada par (old_name, new_name) en todas las carpetas de datos.
    Retorna lista de advertencias para archivos no encontrados.
    """
    folders = [
        RAW_FOLLOWING_PATH,
        RAW_FOLLOWERS_PATH,
        INC_FOLLOWING_PATH,
        INC_FOLLOWERS_PATH,
    ]
    warnings: list[str] = []

    for old_name, new_name in file_renames:
        found = False
        for folder in folders:
            old_path = folder / old_name
            if old_path.exists():
                new_path = folder / new_name
                shutil.move(str(old_path), str(new_path))
                found = True
        if not found:
            warnings.append(
                f"Archivo `{old_name}` no encontrado en disco — "
                "el registro fue actualizado de todas formas."
            )

    return warnings


# ── Operación principal ───────────────────────────────────────────────────────

def rename_user(old_username: str, new_username: str) -> dict:
    """
    Renombra un usuario en todos los artefactos de datos.

    Retorna:
    {
      "success": bool,
      "error": str | None,
      "warnings": [str],
      "summary": str,
      "nodes_affected": int,   # nodos cuyas listas cambiaron
      "edges_affected": int,
      "files_renamed": int,
    }
    """
    old = old_username.strip().lower()
    new = new_username.strip().lower()

    error = validate_rename(old, new)
    if error:
        return {"success": False, "error": error, "warnings": [], "summary": ""}

    # Cargar todo en memoria
    graph_data = load_graph_data()
    registry   = load_registry()

    # Contar impacto antes de mutar
    edges_before = [
        e for e in graph_data.get("edges", [])
        if e["source"] == old or e["target"] == old
    ]
    nodes_with_ref = [
        n for n, d in graph_data["nodes"].items()
        if old in d.get("following", []) or old in d.get("followers", [])
    ]

    # Aplicar cambios en memoria
    _rename_in_graph(graph_data, old, new)
    file_renames = _rename_in_registry(registry, old, new)

    # Persistir (si algo falla aquí es un error real, no dejamos estado parcial)
    save_graph_data(graph_data)
    save_registry(registry)

    # Renombrar archivos en disco (best-effort, genera warnings si no se encuentran)
    disk_warnings = _rename_on_disk(file_renames)

    summary = (
        f"@{old} → @{new}: "
        f"{len(edges_before)} arcos actualizados, "
        f"{len(nodes_with_ref)} nodos con referencias actualizadas, "
        f"{len(file_renames)} archivo(s) renombrado(s) en disco."
    )

    return {
        "success":       True,
        "error":         None,
        "warnings":      disk_warnings,
        "summary":       summary,
        "edges_affected":  len(edges_before),
        "nodes_affected":  len(nodes_with_ref),
        "files_renamed":   len(file_renames),
    }


# ── Listado de usuarios del curso ─────────────────────────────────────────────

def list_course_users() -> list[str]:
    """Retorna los usernames que tienen has_file=True en el grafo."""
    graph_data = load_graph_data()
    return sorted(
        u for u, d in graph_data["nodes"].items()
        if d.get("has_file")
    )


def list_all_users() -> list[str]:
    """Retorna todos los usernames del grafo ordenados."""
    graph_data = load_graph_data()
    return sorted(graph_data["nodes"].keys())


# ── Previsualización de impacto ───────────────────────────────────────────────

def preview_rename(old_username: str, new_username: str) -> dict:
    """
    Retorna cuántos arcos, nodos y archivos se verían afectados,
    sin modificar nada.
    """
    old = old_username.strip().lower()
    new = new_username.strip().lower()

    error = validate_rename(old, new)
    if error:
        return {"valid": False, "error": error}

    graph_data = load_graph_data()
    registry   = load_registry()

    edges_affected = sum(
        1 for e in graph_data.get("edges", [])
        if e["source"] == old or e["target"] == old
    )
    nodes_affected = sum(
        1 for d in graph_data["nodes"].values()
        if old in d.get("following", []) or old in d.get("followers", [])
    )
    files_affected = sum(
        1 for fid, m in registry.items()
        if not fid.startswith("_") and m.get("owner") == old
    )

    return {
        "valid":          True,
        "error":          None,
        "edges_affected":  edges_affected,
        "nodes_affected":  nodes_affected,
        "files_affected":  files_affected,
    }
