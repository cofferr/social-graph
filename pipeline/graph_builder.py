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
    Layout en tres fases que garantiza separación visual entre comunidades.

    Fase 1 — Macro-posiciones de comunidades:
      Cada comunidad recibe un centro en una cuadrícula/círculo de comunidades,
      escalado por el tamaño de la comunidad. Esto crea el "espacio" para que
      spring_layout no los mezcle.

    Fase 2 — Spring local por comunidad:
      Dentro de cada comunidad, spring_layout con k grande para dispersar nodos.
      Las posiciones iniciales se centran en el macro-centro de su comunidad.

    Fase 3 — Interpolación para nodos sin vecinos posicionados:
      Igual que antes — centroide ponderado + jitter radial.

    El resultado: comunidades claramente separadas, con estructura interna
    natural, y nodos puente posicionados entre sus comunidades.
    """
    rng = _random.Random(seed)

    # Agrupar nodos por comunidad
    from collections import defaultdict
    comm_nodes: dict[int, list] = defaultdict(list)
    for node, cid in communities.items():
        if G_ud.has_node(node):
            comm_nodes[cid].append(node)

    n_comms = len(comm_nodes)
    if n_comms == 0:
        return {n: (rng.gauss(0, 1), rng.gauss(0, 1)) for n in G_ud.nodes()}

    # ── Fase 1: macro-posiciones de comunidades ───────────────────────────────
    # spread grande para que los clusters queden bien separados entre sí.
    # El radio base de cada cluster es proporcional a su tamaño para dar espacio real.
    comm_centers: dict[int, tuple] = {}
    sorted_comms = sorted(comm_nodes.keys(), key=lambda c: len(comm_nodes[c]), reverse=True)

    # Spread entre centros de comunidad — aumentado para separar clusters
    spread = max(12.0, math.sqrt(n_comms) * 6.0)

    for i, cid in enumerate(sorted_comms):
        angle = 2 * math.pi * i / n_comms
        # Radio proporcional al tamaño de la comunidad
        size_factor = math.sqrt(len(comm_nodes[cid]) / max(1, len(G_ud)))
        r = spread * (0.8 + 0.5 * size_factor)
        comm_centers[cid] = (r * math.cos(angle), r * math.sin(angle))

    # ── Fase 2: spring local dentro de cada comunidad ─────────────────────────
    pos: dict = {}
    degrees = dict(G_ud.degree())

    for cid, nodes in comm_nodes.items():
        cx, cy = comm_centers[cid]
        n = len(nodes)

        if n == 1:
            pos[nodes[0]] = (cx, cy)
            continue

        sub = G_ud.subgraph(nodes).copy()

        # Radio del cluster más grande para dispersar nodos internamente
        cluster_r = max(2.5, math.sqrt(n) * 0.9)

        # Posiciones iniciales: mini-círculo centrado en comm_center
        init_pos = {}
        for j, node in enumerate(sorted(nodes, key=lambda x: -degrees.get(x, 0))):
            a = 2 * math.pi * j / n
            init_pos[node] = (
                cx + cluster_r * math.cos(a) * rng.uniform(0.6, 1.0),
                cy + cluster_r * math.sin(a) * rng.uniform(0.6, 1.0),
            )

        # k grande = más repulsión interna entre nodos del mismo cluster
        k_val = max(1.5, cluster_r * 3.0 / math.sqrt(n))

        try:
            sub_pos = nx.spring_layout(
                sub,
                k=k_val,
                iterations=120,
                seed=seed + cid,
                weight="weight",
                pos=init_pos,
                center=(cx, cy),
                scale=cluster_r,
            )
            pos.update(sub_pos)
        except Exception:
            for node, p in init_pos.items():
                pos[node] = p

    # ── Fase 3: nodos no posicionados (componentes aisladas) ──────────────────
    remaining = [n for n in G_ud.nodes() if n not in pos]
    xs = [v[0] for v in pos.values()] if pos else [0]
    ys = [v[1] for v in pos.values()] if pos else [0]
    bbox_diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0

    for _ in range(3):
        still = []
        for node in remaining:
            nb_pos = [(pos[nb], degrees.get(nb, 1))
                      for nb in G_ud.neighbors(node) if nb in pos]
            if not nb_pos:
                still.append(node)
                continue
            total_w = sum(w for _, w in nb_pos)
            cx = sum(p[0] * w for p, w in nb_pos) / total_w
            cy = sum(p[1] * w for p, w in nb_pos) / total_w
            jitter = bbox_diag * 0.04 / max(1, math.log1p(len(nb_pos)))
            angle = rng.uniform(0, 2 * math.pi)
            pos[node] = (cx + math.cos(angle) * jitter, cy + math.sin(angle) * jitter)
        remaining = still

    margin = bbox_diag * 0.1
    x_lo, x_hi = min(xs) - margin, max(xs) + margin
    y_lo, y_hi = min(ys) - margin, max(ys) + margin
    for node in remaining:
        pos[node] = (rng.uniform(x_lo, x_hi), rng.uniform(y_lo, y_hi))

    return pos


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

    try:
        k_sample = min(300, G.number_of_nodes())
        betweenness = nx.betweenness_centrality(
            G, normalized=True, weight="weight", k=k_sample, seed=42
        )
    except Exception:
        betweenness = {n: 0.0 for n in G.nodes()}

    try:
        pagerank = nx.pagerank(G, alpha=0.85, weight="weight")
    except Exception:
        pagerank = {n: 0.0 for n in G.nodes()}

    try:
        closeness = nx.closeness_centrality(G)
    except Exception:
        closeness = {n: 0.0 for n in G.nodes()}

    try:
        clustering = nx.clustering(G_ud)
    except Exception:
        clustering = {n: 0.0 for n in G.nodes()}

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

    sigma_nodes = []
    for node in G.nodes():
        x, y = pos.get(node, (0, 0))
        nm   = per_node.get(node, {})
        pr   = nm.get("pagerank", 0)

        has_file     = G.nodes[node].get("has_file", False)
        is_anonymous = G.nodes[node].get("is_anonymous", False)

        # Tamaño por PageRank — course nodes con rango mínimo mayor
        if has_file:
            size = 8 + 12 * (pr - min_pr) / pr_range
        else:
            size = 3 + 8 * (pr - min_pr) / pr_range

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

    # Seguidores compartidos entre pares de estudiantes:
    # Para cada par (A, B) de course nodes, encontrar nodos externos
    # que siguen a ambos o son seguidos por ambos.
    # Estos nodos se marcan is_bridge=True y se posicionan entre A y B.
    course_list = sorted(course_nodes)
    shared_followers: dict[str, set] = {}   # node_id → set of course pairs it bridges
    for i in range(len(course_list)):
        for j in range(i + 1, len(course_list)):
            a, b = course_list[i], course_list[j]
            # Nodos externos que conectan a A y B (en cualquier dirección)
            neighbors_a = set(G.predecessors(a)) | set(G.successors(a))
            neighbors_b = set(G.predecessors(b)) | set(G.successors(b))
            shared = (neighbors_a & neighbors_b) - course_nodes
            for node in shared:
                if node not in shared_followers:
                    shared_followers[node] = set()
                shared_followers[node].add(f"{a}↔{b}")

    # Actualizar atributo bridge en los nodos sigma ya construidos
    bridge_set = set(shared_followers.keys())
    for sn in sigma_nodes:
        sn["is_bridge"] = sn["id"] in bridge_set
        sn["bridges"] = list(shared_followers.get(sn["id"], set()))

    sigma_edges = []
    for i, (src, tgt, data) in enumerate(G.edges(data=True)):
        src_course = src in course_nodes
        tgt_course = tgt in course_nodes
        src_bridge = src in bridge_set
        tgt_bridge = tgt in bridge_set

        # Arco entre dos estudiantes: muy visible
        if src_course and tgt_course:
            color = "rgba(255,255,255,0.55)"
            edge_type = "course_to_course"
        # Arco que conecta un nodo puente con un estudiante: visible
        elif (src_bridge and tgt_course) or (src_course and tgt_bridge):
            color = "rgba(255,255,255,0.18)"
            edge_type = "bridge_to_course"
        # Arco entre dos nodos puente: semivisible
        elif src_bridge and tgt_bridge:
            color = "rgba(255,255,255,0.08)"
            edge_type = "bridge_to_bridge"
        else:
            color = "rgba(255,255,255,0.015)"
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
