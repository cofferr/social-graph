"""
pipeline/graph_builder.py
-------------------------
Construye un grafo NetworkX desde graph_data.json
y calcula métricas por nodo.
"""

import math
import random as _random
import numpy as _np
import networkx as nx
import community as community_louvain
from pipeline.ingestion import load_graph_data

# Azul fijo para nodos del curso
COURSE_NODE_COLOR = "#4e9af1"
COURSE_NODE_COLOR_ANON = "#2a4a6b"

# Paleta para comunidades — debe coincidir con COMMUNITY_COLORS en renderer.py
COMMUNITY_COLORS = [
    "#e63946", "#f4a261", "#2a9d8f", "#e9c46a", "#a8dadc",
    "#6a4c93", "#8ac926", "#ff595e", "#ffca3a", "#6a994e",
    "#bc4749", "#0077b6", "#7b2d8b", "#457b9d", "#1982c4",
]


def calculate_jaccard(set1: set, set2: set) -> float:
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def build_graph(only_course_nodes: bool = False) -> nx.DiGraph:
    """Construye grafo dirigido desde los datos acumulados."""
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
            following_set=set(data.get("following", [])),
            followers_set=set(data.get("followers", []))
        )

    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if only_course_nodes:
            if src not in course_nodes or tgt not in course_nodes:
                continue
        if G.has_node(src) and G.has_node(tgt):
            weight = 1.0
            ts = edge.get("timestamp", 0)
            if G.has_edge(tgt, src):
                G[tgt][src]["weight"] += 0.5
                weight += 0.5
            G.add_edge(src, tgt, weight=weight, timestamp=ts, type="follow")

    return G


# ── Detección de comunidades ──────────────────────────────────────────────────

def _compute_communities(G: nx.DiGraph) -> dict:
    """
    Detecta comunidades con Louvain sobre el grafo no dirigido.

    Louvain maximiza la modularidad — agrupa nodos que tienen más conexiones
    entre sí de las esperadas por azar. Resultado: comunidades estructurales
    reales, no basadas en quién importó el nodo.

    Fallback a Label Propagation si Louvain falla.
    """
    G_ud = G.to_undirected()

    # Construir dict de pesos para python-louvain
    weight_map = {(u, v): d.get("weight", 1.0) for u, v, d in G_ud.edges(data=True)}

    try:
        partition = community_louvain.best_partition(
            G_ud,
            weight="weight",
            resolution=1.0,
            random_state=42,
        )
        # Renumerar comunidades por tamaño descendente para IDs estables
        from collections import Counter
        counts = Counter(partition.values())
        old_to_new = {old: new for new, (old, _) in
                      enumerate(counts.most_common())}
        return {node: old_to_new[cid] for node, cid in partition.items()}
    except Exception:
        pass

    # Fallback: Label Propagation
    try:
        lp_comms = sorted(
            nx.community.label_propagation_communities(G_ud),
            key=len, reverse=True
        )
        result = {}
        for cid, members in enumerate(lp_comms):
            for node in members:
                result[node] = cid
        return result
    except Exception:
        return {n: 0 for n in G.nodes()}


def _assign_owner_community(G: nx.DiGraph) -> dict:
    """
    Asigna a cada nodo el ID (índice 0-based) del owner que lo importó.
    Los nodos del curso reciben su propio índice.
    Los externos heredan el owner con más arcos hacia/desde ellos.
    Útil para la 'Vista por estudiante'.
    """
    owners = sorted(n for n, d in G.nodes(data=True) if d.get("has_file"))
    owner_idx = {o: i for i, o in enumerate(owners)}

    result = {}
    for node, data in G.nodes(data=True):
        if data.get("has_file"):
            result[node] = owner_idx.get(node, 0)
            continue
        # Contar arcos con cada owner
        counts = {}
        for o in owners:
            c = (1 if G.has_edge(node, o) else 0) + (1 if G.has_edge(o, node) else 0)
            if c:
                counts[o] = c
        if counts:
            best = max(counts, key=counts.get)
            result[node] = owner_idx[best]
        else:
            result[node] = 0

    return result


# ── Layout ────────────────────────────────────────────────────────────────────

def _community_aware_layout(G_ud: nx.Graph, communities: dict, seed: int = 42) -> dict:
    """
    Layout rápido y visualmente claro para grafos de hasta decenas de miles de nodos.

    Estrategia (sin spring_layout global, que es O(n²)):
    1. Course nodes en círculo externo amplio — posiciones fijas.
    2. Cada nodo externo se posiciona cerca del centroide de sus vecinos de curso.
       Si no tiene vecinos de curso, se ubica en el sub-círculo de su comunidad.
    3. Dispersión radial según número de vecinos (nodos más conectados al centro).
    4. Para grafos pequeños (≤800 nodos) se añade un spring_layout local
       por comunidad para mejorar la separación interna.
    """
    rng = _random.Random(seed)

    course_nodes_list = sorted(n for n, d in G_ud.nodes(data=True) if d.get("has_file"))
    course_set = set(course_nodes_list)
    n_course = len(course_nodes_list)

    if n_course == 0:
        return nx.spring_layout(G_ud, k=2.0, iterations=50, seed=seed)

    n_total = G_ud.number_of_nodes()
    macro_radius = max(50.0, math.sqrt(n_total) * 3.5)

    # 1. Posiciones de nodos del curso en círculo
    pos: dict[str, _np.ndarray] = {}
    for i, node in enumerate(course_nodes_list):
        angle = 2 * math.pi * i / n_course
        pos[node] = _np.array([macro_radius * math.cos(angle), macro_radius * math.sin(angle)])

    # Precalcular vecinos de curso por nodo externo (una sola pasada)
    course_neighbor_pos: dict[str, list] = {}  # node → [pos arrays of course neighbors]
    for c in course_nodes_list:
        for nb in G_ud.neighbors(c):
            if nb not in course_set:
                course_neighbor_pos.setdefault(nb, []).append(pos[c])

    # Mapa comunidad → posición de curso más representativa
    comm_anchor: dict[int, _np.ndarray] = {}
    for c in course_nodes_list:
        cid = communities.get(c, 0)
        if cid not in comm_anchor:
            comm_anchor[cid] = pos[c]

    # Comunidades sin curso: asignar posición en anillo exterior
    all_comms = set(communities.values())
    missing_comms = all_comms - set(comm_anchor.keys())
    for k, cid in enumerate(sorted(missing_comms)):
        angle = 2 * math.pi * k / max(len(missing_comms), 1)
        comm_anchor[cid] = _np.array([
            macro_radius * 1.6 * math.cos(angle),
            macro_radius * 1.6 * math.sin(angle),
        ])

    # 2. Posición de nodos externos
    for node in G_ud.nodes():
        if node in pos:
            continue
        cid = communities.get(node, 0)
        anchor = comm_anchor.get(cid, _np.zeros(2))

        if node in course_neighbor_pos:
            pts = course_neighbor_pos[node]
            center = _np.mean(pts, axis=0)
            # Dispersión relativa al radio macro: nodos con un solo hub
            # se dispersan más; nodos puente (múltiples hubs) se colocan
            # entre ellos con menor dispersión para no alejarse del centro.
            n_hubs = len(pts)
            spread = macro_radius * (0.30 if n_hubs == 1 else 0.18 / n_hubs + 0.08)
            angle_r = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(spread * 0.3, spread)
            pos[node] = center + _np.array([r * math.cos(angle_r), r * math.sin(angle_r)])
        else:
            # Sin vecinos de curso: sub-anillo alrededor del anchor de comunidad
            angle = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(macro_radius * 0.08, macro_radius * 0.55)
            pos[node] = anchor + _np.array([r * math.cos(angle), r * math.sin(angle)])

    # 3. Para grafos pequeños: refinamiento local por comunidad con spring_layout
    if n_total <= 800:
        from collections import defaultdict
        comm_groups: dict[int, list] = defaultdict(list)
        for node in G_ud.nodes():
            comm_groups[communities.get(node, 0)].append(node)

        for cid, members in comm_groups.items():
            if len(members) < 3:
                continue
            sub = G_ud.subgraph(members)
            init = {m: pos[m] for m in members}
            try:
                refined = nx.spring_layout(sub, pos=init, iterations=25, seed=seed, k=3.0)
                for m, p in refined.items():
                    pos[m] = p
            except Exception:
                pass

    return {node: (float(p[0]), float(p[1])) for node, p in pos.items()}


# ── Helpers de color ──────────────────────────────────────────────────────────

def _desaturate(hex_color: str, factor: float = 0.35) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    gray = int(0.299 * r + 0.587 * g + 0.114 * b)
    r2 = int(r * factor + gray * (1 - factor))
    g2 = int(g * factor + gray * (1 - factor))
    b2 = int(b * factor + gray * (1 - factor))
    return f"#{r2:02x}{g2:02x}{b2:02x}"


# ── Métricas ──────────────────────────────────────────────────────────────────

def compute_metrics(G: nx.DiGraph) -> dict:
    """
    Calcula métricas globales y por nodo.
    Retorna dict con:
      - per_node, global, communities, owner_communities, betweenness
    """
    if G.number_of_nodes() == 0:
        return {"per_node": {}, "global": {}, "communities": {}, "owner_communities": {}}

    in_deg  = dict(G.in_degree())
    out_deg = dict(G.out_degree())
    G_ud    = G.to_undirected()

    n = G.number_of_nodes()

    try:
        # k=min(200, n) gives a fast approximation; exact only for small graphs
        k_sample = min(200, n)
        betweenness = nx.betweenness_centrality(
            G, normalized=True, weight="weight", k=k_sample, seed=42
        )
    except Exception:
        betweenness = {node: 0.0 for node in G.nodes()}

    try:
        pagerank = nx.pagerank(G, alpha=0.85, weight="weight", max_iter=50)
    except Exception:
        pagerank = {node: 0.0 for node in G.nodes()}

    try:
        # closeness_centrality is O(n*m) — skip for large graphs
        if n <= 1500:
            closeness = nx.closeness_centrality(G)
        else:
            # Approximate: sample 300 sources, scale by reachability
            sample = list(G.nodes())[:300]
            closeness = {node: 0.0 for node in G.nodes()}
            for s in sample:
                lengths = nx.single_source_shortest_path_length(G, s)
                for t, d in lengths.items():
                    if d > 0:
                        closeness[t] += 1.0 / d
            max_c = max(closeness.values()) or 1
            closeness = {node: v / max_c for node, v in closeness.items()}
    except Exception:
        closeness = {node: 0.0 for node in G.nodes()}

    try:
        clustering = nx.clustering(G_ud)
    except Exception:
        clustering = {node: 0.0 for node in G.nodes()}

    communities       = _compute_communities(G)
    owner_communities = _assign_owner_community(G)
    owners = [n for n, d in G.nodes(data=True) if d.get("has_file")]

    per_node = {}
    for node in G.nodes():
        per_node[node] = {
            "in_degree":    in_deg.get(node, 0),
            "out_degree":   out_deg.get(node, 0),
            "betweenness":  round(betweenness.get(node, 0), 4),
            "closeness":    round(closeness.get(node, 0), 4),
            "clustering":   round(clustering.get(node, 0), 4),
            "pagerank":     round(pagerank.get(node, 0), 6),
            "community":    communities.get(node, 0),
            "owner_group":  owner_communities.get(node, 0),
            "has_file":     G.nodes[node].get("has_file", False),
            "is_anonymous": G.nodes[node].get("is_anonymous", False),
            "mutual_count": sum(1 for u in G.successors(node) if G.has_edge(node, u) and G.has_edge(u, node)),
        }

    global_metrics = {
        "node_count":        G.number_of_nodes(),
        "edge_count":        G.number_of_edges(),
        "density":           round(nx.density(G), 4),
        "community_count":   len(set(communities.values())),
        "course_node_count": len(owners),
    }

    return {
        "per_node":          per_node,
        "global":            global_metrics,
        "communities":       communities,
        "owner_communities": owner_communities,
        "betweenness":       betweenness,
    }


# ── Serialización para Sigma.js ───────────────────────────────────────────────

# Paleta para la vista por estudiante (owner_group) — colores distintos de la paleta de comunidades
OWNER_COLORS = [
    "#ff6b9d", "#c77dff", "#4cc9f0", "#f72585", "#7209b7",
    "#3a0ca3", "#4361ee", "#4895ef", "#43aa8b", "#90be6d",
    "#f9c74f", "#f8961e",
]


def graph_to_sigma_format(G: nx.DiGraph, metrics: dict) -> dict:
    """
    Serializa el grafo al formato que necesita sigma.js.
    Incluye dos modos de color:
      - color         → comunidades Louvain (modo estructural)
      - owner_color   → quién importó el nodo (modo por estudiante)
    """
    per_node         = metrics.get("per_node", {})
    communities      = metrics.get("communities", {})
    owner_communities = metrics.get("owner_communities", {})
    course_nodes     = {n for n, d in G.nodes(data=True) if d.get("has_file")}

    try:
        pos = _community_aware_layout(G.to_undirected(), communities)
    except Exception:
        rng = _random.Random(42)
        pos = {n: (rng.gauss(0, 1), rng.gauss(0, 1)) for n in G.nodes()}

    pageranks = [per_node[n]["pagerank"] for n in G.nodes() if n in per_node]
    max_pr    = max(pageranks) if pageranks else 1
    min_pr    = min(pageranks) if pageranks else 0
    pr_range  = max_pr - min_pr if max_pr != min_pr else 1
    max_bt    = max((per_node[n]["betweenness"] for n in G.nodes() if n in per_node), default=1) or 1

    # Precalcular bridge_set antes del loop para usarlo en el tamaño de nodo
    course_list_pre = sorted(course_nodes)
    _course_nbrs_pre: dict[str, set] = {
        c: (set(G.predecessors(c)) | set(G.successors(c))) - course_nodes
        for c in course_list_pre
    }
    bridge_set_pre: set[str] = set()
    for i in range(len(course_list_pre)):
        for j in range(i + 1, len(course_list_pre)):
            bridge_set_pre |= _course_nbrs_pre[course_list_pre[i]] & _course_nbrs_pre[course_list_pre[j]]

    sigma_nodes = []
    for node in G.nodes():
        x, y = pos.get(node, (0, 0))
        nm   = per_node.get(node, {})
        pr   = nm.get("pagerank", 0)

        has_file     = G.nodes[node].get("has_file", False)
        is_anonymous = G.nodes[node].get("is_anonymous", False)
        is_bridge    = node in bridge_set_pre

        # Tamaño por PageRank escalado por categoría
        bt = nm.get("betweenness", 0)
        if has_file:
            size = 10 + 16 * (pr - min_pr) / pr_range
        elif is_bridge:
            # Puentes: tamaño base mayor + escala por betweenness (mejor discriminador)
            size = 5 + 8 * (bt / max_bt if max_bt > 0 else 0)
        elif is_anonymous:
            size = 2 + 5 * (pr - min_pr) / pr_range
        else:
            size = 3 + 9 * (pr - min_pr) / pr_range

        # Color modo estructural (Louvain)
        if has_file:
            struct_color = COURSE_NODE_COLOR_ANON if is_anonymous else COURSE_NODE_COLOR
        else:
            cid = communities.get(node, 0)
            base = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
            struct_color = _desaturate(base) if is_anonymous else base

        # Color modo por estudiante
        oid = owner_communities.get(node, 0)
        base_owner = OWNER_COLORS[oid % len(OWNER_COLORS)]
        if has_file:
            owner_color = COURSE_NODE_COLOR  # los del curso siempre azul en este modo
        else:
            owner_color = _desaturate(base_owner) if is_anonymous else base_owner

        sigma_nodes.append({
            "id":            node,
            "label":         node,
            "x":             float(x) * 400,
            "y":             float(y) * 400,
            "size":          round(size, 2),
            "color":         struct_color,
            "owner_color":   owner_color,
            "has_file":      has_file,
            "is_anonymous":  is_anonymous,
            "pagerank":      nm.get("pagerank", 0),
            "community":     communities.get(node, 0),
            "owner_group":   owner_communities.get(node, 0),
            "in_degree":     nm.get("in_degree", 0),
            "out_degree":    nm.get("out_degree", 0),
            "mutual_count":  nm.get("mutual_count", 0),
            "betweenness":   nm.get("betweenness", 0),
            "closeness":     nm.get("closeness", 0),
            "clustering":    nm.get("clustering", 0),
        })

    # Reutilizar los dicts precalculados (_course_nbrs_pre, bridge_set_pre)
    # para construir el mapa node → pares que puentea.
    shared_followers: dict[str, set] = {}
    for i in range(len(course_list_pre)):
        for j in range(i + 1, len(course_list_pre)):
            a, b = course_list_pre[i], course_list_pre[j]
            for node in _course_nbrs_pre[a] & _course_nbrs_pre[b]:
                shared_followers.setdefault(node, set()).add(f"{a}↔{b}")

    bridge_set = bridge_set_pre
    for sn in sigma_nodes:
        sn["is_bridge"] = sn["id"] in bridge_set
        sn["bridges"] = list(shared_followers.get(sn["id"], set()))

    sigma_edges = []
    for i, (src, tgt, data) in enumerate(G.edges(data=True)):
        src_course = src in course_nodes
        tgt_course = tgt in course_nodes
        src_bridge = src in bridge_set
        tgt_bridge = tgt in bridge_set

        # Arco entre dos estudiantes: máximo contraste
        if src_course and tgt_course:
            color = "rgba(255,255,255,0.70)"
            edge_type = "course_to_course"
        # Arco entre estudiante y nodo puente: bien visible
        elif (src_bridge and tgt_course) or (src_course and tgt_bridge):
            color = "rgba(180,160,255,0.30)"
            edge_type = "bridge_to_course"
        # Arco entre dos nodos puente
        elif src_bridge and tgt_bridge:
            color = "rgba(255,255,255,0.10)"
            edge_type = "bridge_to_bridge"
        # Arco donde al menos un extremo es estudiante pero el otro es externo
        elif src_course or tgt_course:
            color = "rgba(100,150,255,0.22)"
            edge_type = "course_to_external"
        else:
            color = "rgba(255,255,255,0.012)"
            edge_type = "external"

        sigma_edges.append({
            "id":        f"e{i}",
            "source":    src,
            "target":    tgt,
            "timestamp": data.get("timestamp", 0),
            "color":     color,
            "edge_type": edge_type,
        })

    return {"nodes": sigma_nodes, "edges": sigma_edges}
