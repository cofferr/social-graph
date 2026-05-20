"""
pipeline/analysis.py
--------------------
Métricas estructurales del grafo para el panel de Análisis.
Separado de graph_builder para mantener responsabilidades claras.
"""

import random
import networkx as nx
import pandas as pd
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe(fn, default=0):
    try:
        return fn()
    except Exception:
        return default


# ── Métricas por nodo ─────────────────────────────────────────────────────────

def compute_degree_centrality(G: nx.DiGraph) -> dict:
    """Fracción de nodos a los que un nodo está conectado (combinando in+out)."""
    return nx.degree_centrality(G)


def compute_in_degree(G: nx.DiGraph) -> dict:
    """Cantidad de arcos entrantes: cuántos nodos siguen a este."""
    return dict(G.in_degree())


def compute_out_degree(G: nx.DiGraph) -> dict:
    """Cantidad de arcos salientes: a cuántos nodos sigue este."""
    return dict(G.out_degree())


def compute_betweenness(G: nx.DiGraph) -> dict:
    """Fracción de caminos más cortos que pasan por este nodo (nodo puente).
    Usa k=300 pivotes para aproximar en <0.5s en lugar de ~8s exacto."""
    return _safe(
        lambda: nx.betweenness_centrality(
            G, normalized=True, weight="weight",
            k=min(300, G.number_of_nodes()), seed=42,
        ),
        {n: 0.0 for n in G.nodes()},
    )


def compute_pagerank(G: nx.DiGraph) -> dict:
    """Importancia relativa según la calidad de quién te sigue (estilo Google)."""
    return _safe(
        lambda: nx.pagerank(G, alpha=0.85, weight="weight"),
        {n: 0.0 for n in G.nodes()},
    )


def compute_closeness(G: nx.DiGraph) -> dict:
    """Qué tan cerca está un nodo de todos los demás en promedio."""
    return _safe(
        lambda: nx.closeness_centrality(G),
        {n: 0.0 for n in G.nodes()},
    )


def compute_clustering(G: nx.DiGraph) -> dict:
    """Qué tan interconectados están los vecinos de un nodo (triángulos)."""
    return _safe(
        lambda: nx.clustering(G.to_undirected()),
        {n: 0.0 for n in G.nodes()},
    )


def compute_reciprocity_per_node(G: nx.DiGraph) -> dict:
    """Fracción de conexiones que son mutuas para cada nodo."""
    result = {}
    for node in G.nodes():
        out_neighbors = set(G.successors(node))
        in_neighbors = set(G.predecessors(node))
        mutual = out_neighbors & in_neighbors
        total = out_neighbors | in_neighbors
        result[node] = len(mutual) / len(total) if total else 0.0
    return result


# ── Métricas globales ─────────────────────────────────────────────────────────

def compute_global_metrics(G: nx.DiGraph) -> dict:
    """Métricas del grafo completo."""
    n = G.number_of_nodes()
    e = G.number_of_edges()

    # Componentes conectadas (débilmente — ignorando dirección)
    wcc = list(nx.weakly_connected_components(G))
    wcc_sorted = sorted(wcc, key=len, reverse=True)

    # Componente principal
    main_component = G.subgraph(wcc_sorted[0]).copy() if wcc_sorted else G

    diameter = None
    avg_path = None
    if main_component.number_of_nodes() > 1:
        G_ud = main_component.to_undirected()
        # Sampling 100 nodos: error <5% y tarda ~0.2s vs ~7s exacto para 3k nodos
        sample_size = min(100, main_component.number_of_nodes())
        sample = random.sample(list(G_ud.nodes()), sample_size)
        total_len, pair_count = 0, 0
        max_dist = 0
        for src in sample:
            lengths = nx.single_source_shortest_path_length(G_ud, src)
            for dist in lengths.values():
                if dist > 0:
                    total_len += dist
                    pair_count += 1
                    if dist > max_dist:
                        max_dist = dist
        avg_path = round(total_len / pair_count, 4) if pair_count else None
        diameter = max_dist if max_dist > 0 else None

    # Reciprocidad global: fracción de arcos con contrapartida
    reciprocity = _safe(lambda: round(nx.reciprocity(G), 4), 0.0)

    return {
        "node_count": n,
        "edge_count": e,
        "density": round(nx.density(G), 4),
        "reciprocity": reciprocity,
        "weakly_connected_components": len(wcc),
        "main_component_size": len(wcc_sorted[0]) if wcc_sorted else 0,
        "diameter": diameter,
        "avg_shortest_path": avg_path,
    }


# ── Análisis enfocado en nodos del curso ──────────────────────────────────────

def build_analysis_dataframe(
    G: nx.DiGraph,
    course_nodes: set,
    precomputed_betweenness: dict | None = None,
) -> pd.DataFrame:
    """
    Calcula todas las métricas por nodo y devuelve un DataFrame.
    Acepta betweenness precomputado para evitar recalcularlo cuando ya lo
    hizo compute_metrics en graph_builder.
    """
    in_deg       = compute_in_degree(G)
    out_deg      = compute_out_degree(G)
    deg_cent     = compute_degree_centrality(G)
    betweenness  = precomputed_betweenness if precomputed_betweenness is not None else compute_betweenness(G)
    pagerank     = compute_pagerank(G)
    closeness    = compute_closeness(G)
    clustering   = compute_clustering(G)
    reciprocity  = compute_reciprocity_per_node(G)

    rows = []
    for node in G.nodes():
        rows.append({
            "usuario":          node,
            "en_curso":         node in course_nodes,
            "in_degree":        in_deg.get(node, 0),
            "out_degree":       out_deg.get(node, 0),
            "degree_centrality": round(deg_cent.get(node, 0), 4),
            "betweenness":      round(betweenness.get(node, 0), 4),
            "pagerank":         round(pagerank.get(node, 0), 6),
            "closeness":        round(closeness.get(node, 0), 4),
            "clustering":       round(clustering.get(node, 0), 4),
            "reciprocity":      round(reciprocity.get(node, 0), 4),
            "mutual_count":     len(set(G.successors(node)) & set(G.predecessors(node))),
        })

    df = pd.DataFrame(rows)
    return df


def get_node_profile(
    G: nx.DiGraph,
    node: str,
    df: pd.DataFrame,
    precomputed_betweenness: dict | None = None,
) -> dict:
    """
    Devuelve métricas + vecinos relevantes para un nodo específico.
    Acepta betweenness precomputado para no recalcular.
    """
    if node not in G.nodes():
        return {}

    row = df[df["usuario"] == node]
    metrics = row.iloc[0].to_dict() if not row.empty else {}

    out_neighbors = list(G.successors(node))
    in_neighbors  = list(G.predecessors(node))
    mutual        = [n for n in out_neighbors if n in G.predecessors(node)]

    betweenness = precomputed_betweenness if precomputed_betweenness is not None else compute_betweenness(G)
    all_neighbors = set(out_neighbors) | set(in_neighbors)
    bridge_nodes = sorted(
        [(n, betweenness.get(n, 0)) for n in all_neighbors],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    return {
        "metrics":      metrics,
        "follows":      out_neighbors,
        "followers":    in_neighbors,
        "mutual":       mutual,
        "bridge_nodes": bridge_nodes,
    }


def get_components_info(G: nx.DiGraph, course_nodes: set) -> list[dict]:
    """
    Descripción de cada componente débilmente conectada.
    Indica cuántos nodos del curso contiene.
    """
    wcc = sorted(nx.weakly_connected_components(G), key=len, reverse=True)
    result = []
    for i, comp in enumerate(wcc):
        course_in_comp = [n for n in comp if n in course_nodes]
        result.append({
            "id":           i,
            "size":         len(comp),
            "course_nodes": course_in_comp,
            "course_count": len(course_in_comp),
            "nodes":        list(comp),
        })
    return result
