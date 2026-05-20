"""
pipeline/ingestion.py
---------------------
Lee archivos JSON de Instagram (following.json / followers.json)
desde una carpeta local o desde archivos subidos en Streamlit.

Reglas de diseño:
- Tolerante: funciona con solo following, solo followers, o ambos.
- Username opcional: si no se declara, se intenta inferir por cruce.
- Deduplicación por hash del contenido (pares username+timestamp).
- Nunca falla silenciosamente: retorna errores descriptivos por archivo.

Formatos soportados:
- Format A (objeto con clave): {"relationships_following": [...]} o {"relationships_followers": [...]}
  Cada entrada: {"title": "username", "string_list_data": [{"timestamp": 123}]}
- Format B (array raíz): [{...}, ...] donde cada entrada tiene "string_list_data" y "media_list_data"
  Cada entrada: {"title": "", "string_list_data": [{"value": "username", "timestamp": 123}]}
"""

import json
import re
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

REGISTRY_PATH    = Path("data/registry/registry.json")
GRAPH_DATA_PATH  = Path("data/graph_data.json")
VERSION_PATH     = Path("data/.version")
DATA_VERSION     = "2"

RAW_FOLLOWING_PATH  = Path("data/raw/following")
RAW_FOLLOWERS_PATH  = Path("data/raw/followers")
INC_FOLLOWING_PATH  = Path("data/incompleto/following")
INC_FOLLOWERS_PATH  = Path("data/incompleto/followers")


# ─── Reset / versioning ───────────────────────────────────────────────────────

def reset_all_data():
    """Borra todos los datos generados: registry, graph, archivos raw e incompleto."""
    REGISTRY_PATH.unlink(missing_ok=True)
    GRAPH_DATA_PATH.unlink(missing_ok=True)

    for folder in (RAW_FOLLOWING_PATH, RAW_FOLLOWERS_PATH,
                   INC_FOLLOWING_PATH, INC_FOLLOWERS_PATH):
        if folder.exists():
            for f in folder.glob("*.json"):
                f.unlink(missing_ok=True)

    # Re-create the folder structure
    for folder in (RAW_FOLLOWING_PATH, RAW_FOLLOWERS_PATH,
                   INC_FOLLOWING_PATH, INC_FOLLOWERS_PATH,
                   REGISTRY_PATH.parent):
        folder.mkdir(parents=True, exist_ok=True)


def check_and_migrate_version():
    """
    Si data/.version no existe o contiene una versión < DATA_VERSION,
    fuerza un reset_all_data() y escribe la versión actual.
    """
    current = VERSION_PATH.read_text().strip() if VERSION_PATH.exists() else "0"
    if current < DATA_VERSION:
        reset_all_data()
        VERSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        VERSION_PATH.write_text(DATA_VERSION)


# ─── Utilidades ──────────────────────────────────────────────────────────────

def _load_json(content: bytes) -> tuple[Optional[dict | list], Optional[str]]:
    """Intenta parsear bytes como JSON. Retorna (data, error)."""
    try:
        return json.loads(content.decode("utf-8")), None
    except Exception as e:
        return None, str(e)


def _stable_id(data: dict | list) -> str:
    """
    Hash determinista basado en los pares (username, timestamp) del archivo.
    Misma persona subiendo dos veces produce el mismo hash → duplicado detectado.
    """
    pairs = []
    if isinstance(data, list):
        entries = data
    else:
        key = "relationships_following" if "relationships_following" in data else "relationships_followers"
        entries = data.get(key, [])

    for entry in entries:
        sld = entry.get("string_list_data", [{}])
        item = sld[0] if sld else {}
        username = item.get("value") or entry.get("title", "")
        ts = item.get("timestamp", 0)
        pairs.append((username, ts))
    pairs.sort()
    raw = json.dumps(pairs, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _detect_file_type(data: dict | list) -> Optional[str]:
    """Detecta si el archivo es 'following', 'followers' o None si es inválido."""
    if isinstance(data, dict):
        if "relationships_following" in data:
            return "following"
        if "relationships_followers" in data:
            return "followers"
        return None
    # Format B: root-level list — only valid for followers
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and "string_list_data" in first and "media_list_data" in first:
            return "followers"
    return None


def _extract_relations(data: dict | list, file_type: str) -> list[dict]:
    """
    Extrae lista de relaciones del JSON (Format A y B).
    Cada relación: {username, timestamp}
    """
    if isinstance(data, list):
        entries = data
    else:
        key = "relationships_following" if file_type == "following" else "relationships_followers"
        entries = data.get(key, [])

    relations = []
    for entry in entries:
        sld = entry.get("string_list_data", [{}])
        item = sld[0] if sld else {}
        username = (item.get("value") or entry.get("title", "")).strip().lower()
        ts = item.get("timestamp", 0)
        if username:
            relations.append({"username": username, "timestamp": ts})
    return relations


def _extract_owner_from_stem(stem: str) -> Optional[str]:
    """
    Extracts owner username from a filename stem, stripping Instagram's
    default naming patterns and numeric-only suffixes.

    Only returns an owner if the remaining suffix contains at least one letter.

    Examples:
      following          → None
      following_jorge    → "jorge"
      following_1        → None
      following (1)      → None
      following1         → None
      followers_1        → None
      followers_1 (2)    → None
      followers_1__3_    → None
      following_jorge2   → "jorge2"
      following_abs      → "abs"
      followers_abs      → "abs"
    """
    s = stem.lower()

    # Strip known base prefixes (longest first)
    for base in ["followers_1", "followers", "following"]:
        if s.startswith(base):
            s = s[len(base):]
            break

    s = re.sub(r'^[\s_]+', '', s)
    s = re.sub(r'[\s_]*\(\d+\)[\s_]*', '', s)   # (2)
    s = re.sub(r'[\s_]*__\d+__[\s_]*', '', s)    # __3__
    s = re.sub(r'[\s_]*__\d+_[\s_]*', '', s)     # __3_
    s = re.sub(r'[\s_]*_\d+__[\s_]*', '', s)     # _3__
    s = re.sub(r'[\s_]+\d+[\s_]*$', '', s)       # trailing " 2", "_2"
    s = re.sub(r'^\d+$', '', s)                   # purely numeric remainder
    s = s.strip('_ \t')

    if s and re.search(r'[a-z]', s):
        return s
    return None


# ─── Registry ────────────────────────────────────────────────────────────────

def load_registry() -> dict:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)
    return {}


def save_registry(registry: dict):
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


# ─── Graph data ──────────────────────────────────────────────────────────────

def load_graph_data() -> dict:
    GRAPH_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if GRAPH_DATA_PATH.exists():
        with open(GRAPH_DATA_PATH, "r") as f:
            return json.load(f)
    return {"nodes": {}, "edges": [], "anonymous_files": []}


def save_graph_data(graph_data: dict):
    with open(GRAPH_DATA_PATH, "w") as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)


# ─── Completitud ─────────────────────────────────────────────────────────────

def get_completeness(registry: Optional[dict] = None) -> dict:
    """
    Returns a dict with owner completeness information.

    Returns:
      {
        "complete": ["alice", "bob"],           # have both file types
        "incomplete": {
          "jorge": {"has": "following", "missing": "followers"},
          "maria": {"has": "followers", "missing": "following"},
        }
      }
    """
    if registry is None:
        registry = load_registry()

    owner_types: dict[str, set] = {}
    for fid, meta in registry.items():
        if fid.startswith("_"):
            continue
        owner = meta.get("owner")
        ft = meta.get("file_type")
        if not owner or not ft:
            continue
        owner_types.setdefault(owner, set()).add(ft)

    complete = []
    incomplete = {}
    for owner, types in owner_types.items():
        if "following" in types and "followers" in types:
            complete.append(owner)
        elif "following" in types:
            incomplete[owner] = {"has": "following", "missing": "followers"}
        else:
            incomplete[owner] = {"has": "followers", "missing": "following"}

    return {"complete": complete, "incomplete": incomplete}


def move_to_incompleto(owner: str, file_type: str, registry: dict):
    """
    Moves raw file for owner+file_type to the incompleto subfolder.
    Updates registry source_path to reflect the new location.
    """
    src_folder = RAW_FOLLOWING_PATH if file_type == "following" else RAW_FOLLOWERS_PATH
    dst_folder = INC_FOLLOWING_PATH if file_type == "following" else INC_FOLLOWERS_PATH
    dst_folder.mkdir(parents=True, exist_ok=True)

    for fid, meta in registry.items():
        if fid.startswith("_"):
            continue
        if meta.get("owner") == owner and meta.get("file_type") == file_type:
            src_name = meta.get("source_name", "")
            src_path = src_folder / src_name
            if src_path.exists():
                dst_path = dst_folder / src_name
                shutil.move(str(src_path), str(dst_path))
                meta["incompleto"] = True


def move_from_incompleto(owner: str, registry: dict):
    """
    Moves all incompleto files for an owner back to the main raw folders.
    Clears the incompleto flag in registry.
    """
    for fid, meta in registry.items():
        if fid.startswith("_"):
            continue
        if meta.get("owner") == owner and meta.get("incompleto"):
            file_type = meta.get("file_type")
            src_folder = INC_FOLLOWING_PATH if file_type == "following" else INC_FOLLOWERS_PATH
            dst_folder = RAW_FOLLOWING_PATH if file_type == "following" else RAW_FOLLOWERS_PATH
            dst_folder.mkdir(parents=True, exist_ok=True)
            src_name = meta.get("source_name", "")
            src_path = src_folder / src_name
            if src_path.exists():
                shutil.move(str(src_path), str(dst_folder / src_name))
            meta.pop("incompleto", None)


def update_completeness_after_ingestion(owner: str, registry: dict):
    """
    After processing a file for `owner`, check if they are now complete or still
    incomplete, and move files accordingly. Saves registry.
    """
    completeness = get_completeness(registry)

    if owner in completeness["complete"]:
        # Ensure any previously-incompleto files are back in raw
        move_from_incompleto(owner, registry)
        # Mark all of owner's registry entries as complete
        for fid, meta in registry.items():
            if fid.startswith("_"):
                continue
            if meta.get("owner") == owner:
                meta["is_complete"] = True
    elif owner in completeness["incomplete"]:
        info = completeness["incomplete"][owner]
        # Move the existing file to incompleto
        move_to_incompleto(owner, info["has"], registry)
        # Mark as incomplete
        for fid, meta in registry.items():
            if fid.startswith("_"):
                continue
            if meta.get("owner") == owner:
                meta["is_complete"] = False


# ─── Inferencia de identidad ─────────────────────────────────────────────────

def _try_infer_owner(
    relations: list[dict],
    file_type: str,
    graph_data: dict,
) -> tuple[Optional[str], float]:
    """
    Returns (owner, confidence) where confidence is in [0, 1].

    Rules:
    - Threshold: 60% overlap AND at least 5 matching relations.
    - Followers boost: if 3+ course nodes appear in the followers file,
      confidence is set to 0.90 (highly diagnostic).
    """
    usernames_in_file = {r["username"] for r in relations}
    known_nodes = graph_data.get("nodes", {})

    best_match: Optional[str] = None
    best_score: float = 0.0
    best_confidence: float = 0.0

    course_nodes_in_file = sum(
        1 for u in usernames_in_file
        if known_nodes.get(u, {}).get("has_file", False)
    )

    for node_username, node_data in known_nodes.items():
        if file_type == "following":
            node_set = set(node_data.get("following", []))
        else:
            node_set = set(node_data.get("followers", []))

        intersection = usernames_in_file & node_set
        match_count = len(intersection)
        score = match_count / max(len(usernames_in_file), 1)

        if score >= 0.60 and match_count >= 5 and score > best_score:
            best_score = score
            best_match = node_username

            if file_type == "followers" and course_nodes_in_file >= 3:
                best_confidence = 0.90
            else:
                best_confidence = score

    return best_match, best_confidence


# ─── Rename anonymous node ───────────────────────────────────────────────────

def _rename_node(graph_data: dict, old_label: str, new_label: str):
    """Renames a node key and updates all edges referencing it."""
    if old_label not in graph_data["nodes"]:
        return
    node = graph_data["nodes"].pop(old_label)
    node["is_anonymous"] = False
    graph_data["nodes"][new_label] = node

    for edge in graph_data["edges"]:
        if edge["source"] == old_label:
            edge["source"] = new_label
        if edge["target"] == old_label:
            edge["target"] = new_label


# ─── Procesamiento de un archivo ─────────────────────────────────────────────

def process_file(
    content: bytes,
    source_name: str,
    declared_owner: Optional[str] = None,
    forced_file_type: Optional[str] = None,
    is_incompleto: bool = False,
    _skip_completeness: bool = False,
) -> dict:
    """
    Procesa un archivo JSON de Instagram.

    Retorna un dict con:
    - status: 'added' | 'duplicate' | 'error' | 'anonymous'
    - message: descripción del resultado
    - file_id: hash del archivo
    - owner: username resuelto
    - file_type: 'following' | 'followers'
    """
    data, error = _load_json(content)
    if error:
        return {"status": "error", "message": f"JSON inválido: {error}", "file_id": None, "owner": None, "file_type": None}

    file_type = forced_file_type or _detect_file_type(data)
    if not file_type:
        return {
            "status": "error",
            "message": "Formato no reconocido. Se esperaba 'relationships_following', 'relationships_followers', o array raíz de Instagram.",
            "file_id": None,
            "owner": None,
            "file_type": None,
        }

    file_id = _stable_id(data)
    registry = load_registry()

    if file_id in registry:
        return {
            "status": "duplicate",
            "message": f"Archivo duplicado. Ya procesado el {registry[file_id]['ingested_at']} (owner: {registry[file_id].get('owner', 'desconocido')}).",
            "file_id": file_id,
            "owner": registry[file_id].get("owner"),
            "file_type": file_type,
        }

    relations = _extract_relations(data, file_type)
    graph_data = load_graph_data()

    # Resolver owner
    owner = declared_owner.strip().lower() if declared_owner else None
    inferred = False
    inference_confidence: float = 1.0 if owner else 0.0

    if not owner:
        owner, inference_confidence = _try_infer_owner(relations, file_type, graph_data)
        if owner:
            inferred = True

    relation_usernames = [r["username"] for r in relations]
    timestamps = {r["username"]: r["timestamp"] for r in relations}

    # Assign anonymous label if still no owner
    assigned_anon_label: Optional[str] = None
    if not owner:
        counter = registry.get("_anon_counter", 0) + 1
        registry["_anon_counter"] = counter
        assigned_anon_label = f"uni{counter}"
        owner = assigned_anon_label

    is_anonymous_node = assigned_anon_label is not None

    # Build the owner node
    if owner not in graph_data["nodes"]:
        graph_data["nodes"][owner] = {
            "following": [],
            "followers": [],
            "has_file": True,
            "is_anonymous": is_anonymous_node,
        }
    else:
        graph_data["nodes"][owner]["has_file"] = True
        if is_anonymous_node:
            graph_data["nodes"][owner]["is_anonymous"] = True

    if file_type == "following":
        existing = set(graph_data["nodes"][owner].get("following", []))
        new_following = [u for u in relation_usernames if u not in existing]
        graph_data["nodes"][owner]["following"] = list(existing | set(relation_usernames))

        for username in new_following:
            if username not in graph_data["nodes"]:
                graph_data["nodes"][username] = {"following": [], "followers": [], "has_file": False}
            graph_data["edges"].append({
                "source": owner,
                "target": username,
                "timestamp": timestamps.get(username, 0),
            })

    else:  # followers
        existing = set(graph_data["nodes"][owner].get("followers", []))
        new_followers = [u for u in relation_usernames if u not in existing]
        graph_data["nodes"][owner]["followers"] = list(existing | set(relation_usernames))

        for username in new_followers:
            if username not in graph_data["nodes"]:
                graph_data["nodes"][username] = {"following": [], "followers": [], "has_file": False}
            graph_data["edges"].append({
                "source": username,
                "target": owner,
                "timestamp": timestamps.get(username, 0),
            })

    if is_anonymous_node:
        graph_data["anonymous_files"].append({
            "file_id": file_id,
            "file_type": file_type,
            "relations": relations,
            "source_name": source_name,
            "assigned_owner": assigned_anon_label,
        })
    else:
        _resolve_anonymous(graph_data, registry)

    save_graph_data(graph_data)

    registry[file_id] = {
        "source_name": source_name,
        "file_type": file_type,
        "owner": owner,
        "inferred_owner": inferred,
        "inference_confidence": round(inference_confidence, 4),
        "relation_count": len(relations),
        "ingested_at": datetime.now().isoformat(timespec="seconds"),
        "is_complete": None,   # filled in by update_completeness_after_ingestion
        "incompleto": is_incompleto,
    }

    # Update completeness only for non-anonymous owners (unless caller defers it)
    if not is_anonymous_node and not _skip_completeness:
        update_completeness_after_ingestion(owner, registry)

    save_registry(registry)

    status = "anonymous" if is_anonymous_node else "added"
    msg = (
        f"Procesado: {len(relations)} relaciones de '{file_type}'."
        + (f" Owner inferido automáticamente: @{owner} (confianza: {inference_confidence:.0%})." if inferred else "")
        + (f" Owner declarado: @{owner}." if not inferred and not is_anonymous_node else "")
        + (f" Sin owner identificado — asignado como @{assigned_anon_label} para resolución futura." if is_anonymous_node else "")
    )

    return {"status": status, "message": msg, "file_id": file_id, "owner": owner, "file_type": file_type}


def _resolve_anonymous(graph_data: dict, registry: Optional[dict] = None):
    """Intenta resolver archivos anónimos pendientes con la info actual del grafo."""
    if registry is None:
        registry = load_registry()

    still_anonymous = []
    registry_changed = False

    for anon in graph_data.get("anonymous_files", []):
        relations = anon["relations"]
        file_type = anon["file_type"]
        assigned_owner = anon.get("assigned_owner")

        real_owner, confidence = _try_infer_owner(relations, file_type, graph_data)

        if real_owner and real_owner != assigned_owner:
            if assigned_owner and assigned_owner in graph_data["nodes"]:
                _rename_node(graph_data, assigned_owner, real_owner)
            else:
                relation_usernames = [r["username"] for r in relations]
                timestamps = {r["username"]: r["timestamp"] for r in relations}
                if real_owner not in graph_data["nodes"]:
                    graph_data["nodes"][real_owner] = {"following": [], "followers": [], "has_file": True}
                else:
                    graph_data["nodes"][real_owner]["has_file"] = True

                if file_type == "following":
                    existing = set(graph_data["nodes"][real_owner].get("following", []))
                    for u in [x for x in relation_usernames if x not in existing]:
                        if u not in graph_data["nodes"]:
                            graph_data["nodes"][u] = {"following": [], "followers": [], "has_file": False}
                        graph_data["edges"].append({"source": real_owner, "target": u, "timestamp": timestamps.get(u, 0)})
                    graph_data["nodes"][real_owner]["following"] = list(existing | set(relation_usernames))
                else:
                    existing = set(graph_data["nodes"][real_owner].get("followers", []))
                    for u in [x for x in relation_usernames if x not in existing]:
                        if u not in graph_data["nodes"]:
                            graph_data["nodes"][u] = {"following": [], "followers": [], "has_file": False}
                        graph_data["edges"].append({"source": u, "target": real_owner, "timestamp": timestamps.get(u, 0)})
                    graph_data["nodes"][real_owner]["followers"] = list(existing | set(relation_usernames))

            file_id = anon["file_id"]
            if file_id in registry:
                registry[file_id]["owner"] = real_owner
                registry[file_id]["inferred_owner"] = True
                registry[file_id]["inference_confidence"] = round(confidence, 4)
                registry_changed = True
        else:
            still_anonymous.append(anon)

    graph_data["anonymous_files"] = still_anonymous
    if registry_changed:
        save_registry(registry)


# ─── Escaneo de carpetas locales ──────────────────────────────────────────────

def _scan_subfolder(folder: Path, forced_file_type: str, is_incompleto: bool = False) -> list[dict]:
    """
    Escanea una subcarpeta y procesa todos los JSON.
    El tipo de archivo viene forzado por la carpeta.
    El owner se infiere del nombre del archivo usando _extract_owner_from_stem.
    """
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        return []

    results = []
    for filepath in sorted(folder.glob("*.json")):
        with open(filepath, "rb") as f:
            content = f.read()

        owner = _extract_owner_from_stem(filepath.stem)

        result = process_file(
            content,
            source_name=filepath.name,
            declared_owner=owner,
            forced_file_type=forced_file_type,
            is_incompleto=is_incompleto,
        )
        result["source_name"] = filepath.name
        results.append(result)

    return results


def scan_local_folder() -> list[dict]:
    """
    Escanea data/raw/following/, data/raw/followers/,
    data/incompleto/following/ y data/incompleto/followers/.
    Retorna lista unificada de resultados por archivo.
    """
    results = []
    results.extend(_scan_subfolder(RAW_FOLLOWING_PATH, "following", is_incompleto=False))
    results.extend(_scan_subfolder(RAW_FOLLOWERS_PATH, "followers", is_incompleto=False))
    results.extend(_scan_subfolder(INC_FOLLOWING_PATH, "following", is_incompleto=True))
    results.extend(_scan_subfolder(INC_FOLLOWERS_PATH, "followers", is_incompleto=True))
    return results


# ─── Upload emparejado ────────────────────────────────────────────────────────

def process_paired_upload(
    username: str,
    following_content: Optional[bytes],
    following_name: str,
    followers_content: Optional[bytes],
    followers_name: str,
) -> dict:
    """
    Procesa un par de archivos subidos juntos con un username declarado.

    Saves files to disk first with canonical names, then processes them.
    Completeness is evaluated once after both files are handled.

    Returns:
    {
      "results": [result_dict, ...],   # one per file processed
      "is_complete": bool,
      "owner": str,
    }
    """
    owner = username.strip().lower()
    results = []

    # Save to disk first with canonical names so completeness moves can find them
    following_disk_name: Optional[str] = None
    followers_disk_name: Optional[str] = None

    if following_content:
        RAW_FOLLOWING_PATH.mkdir(parents=True, exist_ok=True)
        following_disk_name = f"following_{owner}.json"
        (RAW_FOLLOWING_PATH / following_disk_name).write_bytes(following_content)

    if followers_content:
        RAW_FOLLOWERS_PATH.mkdir(parents=True, exist_ok=True)
        followers_disk_name = f"followers_{owner}.json"
        (RAW_FOLLOWERS_PATH / followers_disk_name).write_bytes(followers_content)

    # Process files (skip per-file completeness; we'll do it once at the end)
    if following_content and following_disk_name:
        r = process_file(
            following_content,
            source_name=following_disk_name,
            declared_owner=owner,
            forced_file_type="following",
            _skip_completeness=True,
        )
        results.append(r)

    if followers_content and followers_disk_name:
        r = process_file(
            followers_content,
            source_name=followers_disk_name,
            declared_owner=owner,
            forced_file_type="followers",
            _skip_completeness=True,
        )
        results.append(r)

    # Single completeness evaluation after all files are processed
    registry = load_registry()
    completeness = get_completeness(registry)
    is_complete = owner in completeness["complete"]

    update_completeness_after_ingestion(owner, registry)
    save_registry(registry)

    return {"results": results, "is_complete": is_complete, "owner": owner}
