"""
pipeline/graph_builder.py
-------------------------
Construye un grafo NetworkX desde graph_data.json
y calcula métricas por nodo.
"""

import networkx as nx
import community as community_louvain
from pipeline.ingestion import load_graph_data


def build_graph(only_course_nodes: bool = False) -> nx.DiGraph:
    """
    Construye grafo dirigido desde los datos acumulados.

    only_course_nodes: si True, filtra nodos que no tienen archivo propio
    (es decir, solo muestra personas del curso que subieron su archivo).
    """
    graph_data = load_graph_data()
    G = nx.DiGraph()

    nodes = graph_data.get("nodes", {})
    edges = graph_data.get("edges", [])

    course_nodes = {u for u, d in nodes.items() if d.get("has_file")}

    for username, data in nodes.items():
        if only_course_nodes and username not in course_nodes:
            continue
        G.add_node(
            username,
            has_file=data.get("has_file", False),
            is_anonymous=data.get("is_anonymous", False),
            following_count=len(data.get("following", [])),
            followers_count=len(data.get("followers", [])),
        )

    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if only_course_nodes:
            if src not in course_nodes or tgt not in course_nodes:
                continue
        if G.has_node(src) and G.has_node(tgt):
            G.add_edge(src, tgt, timestamp=edge.get("timestamp", 0))

    return G


def compute_metrics(G: nx.DiGraph) -> dict:
    """
    Calcula métricas globales y por nodo.
    Retorna dict con:
      - per_node: {username: {metric: value}}
      - global: {metric: value}
      - communities: {username: community_id}
    """
    if G.number_of_nodes() == 0:
        return {"per_node": {}, "global": {}, "communities": {}}

    # Métricas por nodo
    in_deg = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    # Centralidades (sobre grafo no dirigido para algunas)
    G_undirected = G.to_undirected()

    try:
        betweenness = nx.betweenness_centrality(G, normalized=True)
    except Exception:
        betweenness = {n: 0 for n in G.nodes()}

    try:
        closeness = nx.closeness_centrality(G)
    except Exception:
        closeness = {n: 0 for n in G.nodes()}

    try:
        clustering = nx.clustering(G_undirected)
    except Exception:
        clustering = {n: 0 for n in G.nodes()}

    try:
        pagerank = nx.pagerank(G, alpha=0.85)
    except Exception:
        pagerank = {n: 0 for n in G.nodes()}

    # Comunidades (Louvain, sobre grafo no dirigido)
    communities = {}
    try:
        partition = community_louvain.best_partition(G_undirected)
        communities = partition
    except Exception:
        communities = {n: 0 for n in G.nodes()}

    per_node = {}
    for node in G.nodes():
        # Vecinos directos
        successors = list(G.successors(node))    # a quienes sigue
        predecessors = list(G.predecessors(node)) # quienes lo siguen

        # Mutualidad: siguen en ambas direcciones
        mutual = [u for u in successors if u in predecessors]

        per_node[node] = {
            "in_degree": in_deg.get(node, 0),
            "out_degree": out_deg.get(node, 0),
            "betweenness": round(betweenness.get(node, 0), 4),
            "closeness": round(closeness.get(node, 0), 4),
            "clustering": round(clustering.get(node, 0), 4),
            "pagerank": round(pagerank.get(node, 0), 6),
            "mutual_count": len(mutual),
            "mutual_with": mutual,
            "follows": successors,
            "followed_by": predecessors,
            "community": communities.get(node, 0),
            "has_file": G.nodes[node].get("has_file", False),
            "is_anonymous": G.nodes[node].get("is_anonymous", False),
        }

    # Métricas globales
    global_metrics = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "density": round(nx.density(G), 4),
        "community_count": len(set(communities.values())),
        "course_node_count": sum(1 for n in G.nodes() if G.nodes[n].get("has_file")),
    }

    try:
        global_metrics["avg_clustering"] = round(nx.average_clustering(G_undirected), 4)
    except Exception:
        global_metrics["avg_clustering"] = 0

    return {
        "per_node": per_node,
        "global": global_metrics,
        "communities": communities,
    }


def _desaturate(hex_color: str, factor: float = 0.35) -> str:
    """Return a desaturated version of a hex color for anonymous nodes."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    gray = int(0.299 * r + 0.587 * g + 0.114 * b)
    r2 = int(r * factor + gray * (1 - factor))
    g2 = int(g * factor + gray * (1 - factor))
    b2 = int(b * factor + gray * (1 - factor))
    return f"#{r2:02x}{g2:02x}{b2:02x}"


def graph_to_sigma_format(G: nx.DiGraph, metrics: dict) -> dict:
    """
    Serializa el grafo al formato que necesita sigma.js:
    { nodes: [{id, label, x, y, size, color, ...attrs}], edges: [{id, source, target}] }

    Usa spring layout para posiciones iniciales.
    """
    import math
    import random

    community_colors = [
        "#e63946", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261",
        "#a8dadc", "#6a4c93", "#1982c4", "#8ac926", "#ff595e",
        "#ffca3a", "#6a994e", "#bc4749", "#0077b6", "#7b2d8b",
    ]

    per_node = metrics.get("per_node", {})
    communities = metrics.get("communities", {})

    # Layout con spring para posiciones legibles
    try:
        pos = nx.spring_layout(G, k=2.5, iterations=80, seed=42)
    except Exception:
        pos = {n: (random.random(), random.random()) for n in G.nodes()}

    # Normalizar pagerank para tamaño de nodo
    pageranks = [per_node[n]["pagerank"] for n in G.nodes() if n in per_node]
    max_pr = max(pageranks) if pageranks else 1
    min_pr = min(pageranks) if pageranks else 0
    pr_range = max_pr - min_pr if max_pr != min_pr else 1

    sigma_nodes = []
    for node in G.nodes():
        x, y = pos.get(node, (0, 0))
        node_metrics = per_node.get(node, {})
        pr = node_metrics.get("pagerank", 0)
        size = 6 + 20 * (pr - min_pr) / pr_range
        community_id = communities.get(node, 0)
        color = community_colors[community_id % len(community_colors)]
        has_file = G.nodes[node].get("has_file", False)
        is_anonymous = G.nodes[node].get("is_anonymous", False)

        # Desaturate color for anonymous nodes
        if is_anonymous:
            node_color = _desaturate(color)
        else:
            node_color = color

        sigma_nodes.append({
            "id": node,
            "label": node,
            "x": float(x) * 1000,
            "y": float(y) * 1000,
            "size": round(size, 2),
            "color": node_color,
            "has_file": has_file,
            "is_anonymous": is_anonymous,
            "in_degree": node_metrics.get("in_degree", 0),
            "out_degree": node_metrics.get("out_degree", 0),
            "betweenness": node_metrics.get("betweenness", 0),
            "closeness": node_metrics.get("closeness", 0),
            "clustering": node_metrics.get("clustering", 0),
            "pagerank": node_metrics.get("pagerank", 0),
            "mutual_count": node_metrics.get("mutual_count", 0),
            "community": community_id,
        })

    sigma_edges = []
    for i, (src, tgt, data) in enumerate(G.edges(data=True)):
        sigma_edges.append({
            "id": f"e{i}",
            "source": src,
            "target": tgt,
            "timestamp": data.get("timestamp", 0),
        })

    return {"nodes": sigma_nodes, "edges": sigma_edges}
