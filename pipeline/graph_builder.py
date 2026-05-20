"""
pipeline/graph_builder.py
-------------------------
Construye un grafo NetworkX desde graph_data.json
y calcula métricas por nodo.
"""

import networkx as nx
import community as community_louvain
from pipeline.ingestion import load_graph_data

SIMILARITY_THRESHOLD = 0.08

def calculate_jaccard(set1: set, set2: set) -> float:
    """Calcula la similitud de Jaccard entre dos conjuntos."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0

def build_graph(only_course_nodes: bool = False) -> nx.DiGraph:
    """
    Construye grafo dirigido desde los datos acumulados.
    
    Incluye lógica de pesos y arcos de similitud entre owners.
    """
    graph_data = load_graph_data()
    G = nx.DiGraph()

    nodes = graph_data.get("nodes", {})
    edges = graph_data.get("edges", [])

    course_nodes = {u for u, d in nodes.items() if d.get("has_file")}

    # 1. Agregar nodos
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

    # 2. Agregar arcos de follow con pesos
    # Bonus de mutualidad y timestamps
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if only_course_nodes:
            if src not in course_nodes or tgt not in course_nodes:
                continue
        if G.has_node(src) and G.has_node(tgt):
            weight = 1.0
            ts = edge.get("timestamp", 0)
            
            # Si ya existe el arco inverso (mutual), subimos peso
            if G.has_edge(tgt, src):
                G[tgt][src]["weight"] += 0.5
                weight += 0.5
            
            G.add_edge(src, tgt, weight=weight, timestamp=ts, type="follow")

    # 3. Agregar arcos de similitud entre owners (solo para layout/comunidades interno)
    # Nota: No los agregamos a G directamente para no ensuciar los arcos dirigidos de follow,
    # pero los usaremos en compute_metrics para el grafo de Louvain.
    
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

    G_undirected = G.to_undirected()

    try:
        betweenness = nx.betweenness_centrality(G, normalized=True, weight="weight")
    except Exception:
        betweenness = {n: 0 for n in G.nodes()}

    try:
        pagerank = nx.pagerank(G, alpha=0.85, weight="weight")
    except Exception:
        pagerank = {n: 0 for n in G.nodes()}

    try:
        closeness = nx.closeness_centrality(G)
    except Exception:
        closeness = {n: 0 for n in G.nodes()}

    try:
        clustering = nx.clustering(G_undirected)
    except Exception:
        clustering = {n: 0 for n in G.nodes()}

    # --- COMUNIDADES POR SIMILITUD ---
    # Creamos un grafo de similitud solo para Louvain
    G_sim = nx.Graph()
    owners = [n for n, d in G.nodes(data=True) if d.get("has_file")]
    
    # Agregar nodos owners a G_sim
    for o in owners:
        G_sim.add_node(o)

    # Calcular similitudes entre todos los pares de owners
    for i in range(len(owners)):
        for j in range(i + 1, len(owners)):
            u1, u2 = owners[i], owners[j]
            # Combinamos following y followers para una firma social completa
            set1 = G.nodes[u1]["following_set"] | G.nodes[u1]["followers_set"]
            set2 = G.nodes[u2]["following_set"] | G.nodes[u2]["followers_set"]
            
            sim = calculate_jaccard(set1, set2)
            
            if sim >= SIMILARITY_THRESHOLD:
                # Bonus por proximidad temporal en follows compartidos
                # Si ambos siguieron a las mismas personas en fechas cercanas
                common = set1 & set2
                ts_bonus = 0.0
                for c_node in common:
                    # Buscamos timestamps en G
                    # A -> x
                    ts1 = 0
                    if G.has_edge(u1, c_node): ts1 = G[u1][c_node].get("timestamp", 0)
                    elif G.has_edge(c_node, u1): ts1 = G[c_node][u1].get("timestamp", 0)
                    
                    ts2 = 0
                    if G.has_edge(u2, c_node): ts2 = G[u2][c_node].get("timestamp", 0)
                    elif G.has_edge(c_node, u2): ts2 = G[c_node][u2].get("timestamp", 0)
                    
                    if ts1 > 0 and ts2 > 0:
                        diff_days = abs(ts1 - ts2) / 86400
                        if diff_days < 7: # Bonus si siguieron en la misma semana
                            ts_bonus += 0.05
                
                G_sim.add_edge(u1, u2, weight=sim + min(ts_bonus, 0.5))

    # Louvain sobre owners
    communities = {}
    try:
        if G_sim.number_of_edges() > 0:
            partition = community_louvain.best_partition(G_sim, weight="weight")
            communities = partition
        else:
            communities = {n: 0 for n in owners}
    except Exception:
        communities = {n: 0 for n in owners}

    # Propagar comunidades a nodos externos
    # Un nodo externo toma la comunidad más frecuente entre los owners con los que conecta
    for node in G.nodes():
        if node in communities:
            continue
            
        # Vecinos que son owners
        neighbors = set(G.successors(node)) | set(G.predecessors(node))
        owner_neighbors = [n for n in neighbors if n in communities]
        
        if owner_neighbors:
            neighbor_communities = [communities[n] for n in owner_neighbors]
            communities[node] = max(set(neighbor_communities), key=neighbor_communities.count)
        else:
            communities[node] = 0 # Comunidad default

    per_node = {}
    for node in G.nodes():
        per_node[node] = {
            "in_degree": in_deg.get(node, 0),
            "out_degree": out_deg.get(node, 0),
            "betweenness": round(betweenness.get(node, 0), 4),
            "closeness": round(closeness.get(node, 0), 4),
            "clustering": round(clustering.get(node, 0), 4),
            "pagerank": round(pagerank.get(node, 0), 6),
            "community": communities.get(node, 0),
            "has_file": G.nodes[node].get("has_file", False),
            "is_anonymous": G.nodes[node].get("is_anonymous", False),
            "mutual_count": len([u for u in G.successors(node) if u in G.predecessors(node)]),
        }

    global_metrics = {
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
        "density": round(nx.density(G), 4),
        "community_count": len(set(communities.values())),
        "course_node_count": len(owners),
    }

    return {
        "per_node": per_node,
        "global": global_metrics,
        "communities": communities,
        "G_sim": G_sim # Retornamos esto para el layout si es necesario
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
    Serializa el grafo al formato que necesita sigma.js.
    Mejora la dispersión del layout.
    """
    import random

    community_colors = [
        "#e63946", "#457b9d", "#2a9d8f", "#e9c46a", "#f4a261",
        "#a8dadc", "#6a4c93", "#1982c4", "#8ac926", "#ff595e",
        "#ffca3a", "#6a994e", "#bc4749", "#0077b6", "#7b2d8b",
    ]

    per_node = metrics.get("per_node", {})
    communities = metrics.get("communities", {})
    G_sim = metrics.get("G_sim", nx.Graph())

    # --- LAYOUT HÍBRIDO ---
    # Para el layout, creamos un grafo que combine follows (pesados) y similitud (muy pesados)
    # Esto forzará a que los clusters de similitud se agrupen fuertemente.
    G_layout = G.to_undirected()
    for u, v, d in G_sim.edges(data=True):
        if G_layout.has_edge(u, v):
            G_layout[u][v]["weight"] = G_layout[u][v].get("weight", 1.0) + d["weight"] * 10
        else:
            G_layout.add_edge(u, v, weight=d["weight"] * 10)

    try:
        # k: repulsión. iterations: estabilidad.
        pos = nx.spring_layout(G_layout, k=3.5, iterations=100, seed=42, weight="weight")
    except Exception:
        pos = {n: (random.random(), random.random()) for n in G.nodes()}

    # Normalizar pagerank para tamaño de nodo (con límites para evitar gigantes)
    pageranks = [per_node[n]["pagerank"] for n in G.nodes() if n in per_node]
    max_pr = max(pageranks) if pageranks else 1
    min_pr = min(pageranks) if pageranks else 0
    pr_range = max_pr - min_pr if max_pr != min_pr else 1

    sigma_nodes = []
    for node in G.nodes():
        x, y = pos.get(node, (0, 0))
        node_metrics = per_node.get(node, {})
        pr = node_metrics.get("pagerank", 0)
        
        # Tamaño más consistente: entre 4 y 18
        size = 4 + 14 * (pr - min_pr) / pr_range
        
        community_id = communities.get(node, 0)
        color = community_colors[community_id % len(community_colors)]
        has_file = G.nodes[node].get("has_file", False)
        is_anonymous = G.nodes[node].get("is_anonymous", False)

        if is_anonymous:
            node_color = _desaturate(color)
        else:
            node_color = color

        sigma_nodes.append({
            "id": node,
            "label": node,
            "x": float(x) * 1500, # Escala aumentada para dispersión
            "y": float(y) * 1500,
            "size": round(size, 2),
            "color": node_color,
            "has_file": has_file,
            "is_anonymous": is_anonymous,
            "pagerank": node_metrics.get("pagerank", 0),
            "community": community_id,
            "in_degree": node_metrics.get("in_degree", 0),
            "out_degree": node_metrics.get("out_degree", 0),
            "mutual_count": node_metrics.get("mutual_count", 0),
            "betweenness": node_metrics.get("betweenness", 0),
            "closeness": node_metrics.get("closeness", 0),
            "clustering": node_metrics.get("clustering", 0),
        })

    sigma_edges = []
    for i, (src, tgt, data) in enumerate(G.edges(data=True)):
        sigma_edges.append({
            "id": f"e{i}",
            "source": src,
            "target": tgt,
            "timestamp": data.get("timestamp", 0),
            "color": "rgba(255,255,255,0.05)" # Mucho más transparente
        })

    return {"nodes": sigma_nodes, "edges": sigma_edges}
