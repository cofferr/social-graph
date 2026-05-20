"""
viz/renderer.py
---------------
Genera el HTML del componente Sigma.js para embeber en Streamlit.
"""

import json


def build_sigma_html(graph_json: dict, height: int = 700) -> str:
    """
    Genera un componente HTML completo con Sigma.js v3 + Graphology.
    Características:
    - Renderizado WebGL
    - Click en nodo → panel lateral con métricas
    - Hover → highlight de conexiones directas
    - Filtros por tipo de nodo (Todos / Solo curso / Mutuos)
    - Filtros por comunidad (toggle por comunidad, apilables)
    - Aislamiento de vecinos y de comunidad desde el panel
    - Botón Reset para limpiar todos los filtros activos
    - Búsqueda de nodo
    - Zoom / pan nativos
    """
    graph_str = json.dumps(graph_json)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: #0a0a0f;
    color: #e8e8f0;
    font-family: 'DM Sans', sans-serif;
    overflow: hidden;
    height: {height}px;
  }}

  #container {{
    display: flex;
    width: 100%;
    height: {height}px;
    position: relative;
  }}

  #sigma-container {{
    flex: 1;
    background: #0a0a0f;
    position: relative;
    overflow: hidden;
  }}

  /* ── Toolbar ─────────────────────────────────────────────────────────────── */
  #toolbar {{
    position: absolute;
    top: 16px;
    left: 16px;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 420px;
  }}

  #search-box {{
    background: rgba(20,20,32,0.92);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px;
    padding: 8px 12px;
    color: #e8e8f0;
    font-family: 'Space Mono', monospace;
    font-size: 12px;
    width: 200px;
    outline: none;
    transition: border-color 0.2s;
  }}
  #search-box:focus {{ border-color: rgba(255,255,255,0.35); }}
  #search-box::placeholder {{ color: rgba(255,255,255,0.3); }}

  .filter-row {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    align-items: center;
  }}

  .filter-btn {{
    background: rgba(20,20,32,0.88);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    color: #e8e8f0;
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    padding: 5px 10px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }}
  .filter-btn:hover {{
    border-color: rgba(255,255,255,0.35);
    background: rgba(40,40,60,0.9);
  }}
  .filter-btn.active {{
    border-color: #7c6fff;
    background: rgba(124,111,255,0.2);
    color: #b8b0ff;
  }}

  /* Community buttons: colored left border */
  .comm-btn {{
    border-left-width: 3px !important;
    border-left-style: solid !important;
    padding-left: 8px !important;
  }}

  /* Reset button */
  #reset-btn {{
    opacity: 0.65;
  }}
  #reset-btn:hover {{
    opacity: 1;
  }}

  /* ── Isolation banner ────────────────────────────────────────────────────── */
  #isolation-banner {{
    display: none;
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 20;
    background: rgba(10,10,25,0.93);
    border-bottom: 2px solid #7c6fff;
    padding: 7px 16px;
    font-family: 'Space Mono', monospace;
    font-size: 11px;
    color: #b8b0ff;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }}
  #isolation-banner.visible {{
    display: flex;
  }}
  #isolation-exit {{
    background: none;
    border: 1px solid rgba(124,111,255,0.4);
    border-radius: 4px;
    color: #b8b0ff;
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    padding: 3px 10px;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
  }}
  #isolation-exit:hover {{
    background: rgba(124,111,255,0.2);
  }}

  /* ── Panel lateral ───────────────────────────────────────────────────────── */
  #panel {{
    width: 0;
    overflow: hidden;
    background: rgba(10,10,20,0.97);
    border-left: 1px solid rgba(255,255,255,0.08);
    transition: width 0.3s cubic-bezier(0.4,0,0.2,1);
    display: flex;
    flex-direction: column;
    position: relative;
    flex-shrink: 0;
  }}
  #panel.open {{ width: 280px; }}

  #panel-inner {{
    padding: 24px 20px;
    width: 280px;
    overflow-y: auto;
    height: 100%;
  }}
  #panel-inner::-webkit-scrollbar {{ width: 3px; }}
  #panel-inner::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 2px; }}

  #panel-close {{
    position: absolute;
    top: 12px;
    right: 12px;
    background: none;
    border: none;
    color: rgba(255,255,255,0.4);
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
    padding: 4px;
    transition: color 0.15s;
    z-index: 2;
  }}
  #panel-close:hover {{ color: #e8e8f0; }}

  .panel-username {{
    font-family: 'Space Mono', monospace;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 4px;
    word-break: break-all;
  }}
  .panel-username::before {{
    content: '@';
    color: #7c6fff;
  }}

  .panel-badge {{
    display: inline-block;
    font-size: 9px;
    font-family: 'Space Mono', monospace;
    padding: 2px 7px;
    border-radius: 4px;
    margin-bottom: 16px;
    font-weight: 700;
    letter-spacing: 0.05em;
  }}
  .badge-course  {{ background: rgba(124,111,255,0.2); color: #b8b0ff; border: 1px solid rgba(124,111,255,0.4); }}
  .badge-external {{ background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.4); border: 1px solid rgba(255,255,255,0.1); }}
  .badge-anon   {{ background: rgba(255,200,0,0.1); color: #ffd166; border: 1px solid rgba(255,209,102,0.3); }}

  .metric-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 16px;
  }}

  .metric-card {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 8px;
    padding: 10px 12px;
  }}
  .metric-label {{
    font-size: 9px;
    font-family: 'Space Mono', monospace;
    color: rgba(255,255,255,0.35);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
  }}
  .metric-value {{
    font-size: 18px;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    color: #e8e8f0;
  }}
  .metric-value.small {{ font-size: 13px; }}

  /* Panel action buttons */
  .panel-action-row {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 16px;
  }}
  .panel-action-btn {{
    width: 100%;
    background: rgba(20,20,32,0.88);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    color: #e8e8f0;
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    padding: 7px 10px;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
  }}
  .panel-action-btn:hover {{
    border-color: rgba(255,255,255,0.35);
    background: rgba(40,40,60,0.9);
  }}
  .panel-action-btn.active {{
    border-color: #7c6fff;
    background: rgba(124,111,255,0.2);
    color: #b8b0ff;
  }}

  .section-title {{
    font-size: 9px;
    font-family: 'Space Mono', monospace;
    color: rgba(255,255,255,0.3);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 10px;
  }}

  .node-list {{
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 20px;
    max-height: 140px;
    overflow-y: auto;
  }}
  .node-list::-webkit-scrollbar {{ width: 3px; }}
  .node-list::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 2px; }}

  .node-chip {{
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    color: rgba(255,255,255,0.6);
    padding: 4px 8px;
    background: rgba(255,255,255,0.04);
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .node-chip:hover {{ background: rgba(124,111,255,0.15); color: #b8b0ff; }}

  .divider {{
    border: none;
    border-top: 1px solid rgba(255,255,255,0.06);
    margin: 14px 0;
  }}

  /* ── Stats bar ───────────────────────────────────────────────────────────── */
  #stats-bar {{
    position: absolute;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(10,10,20,0.85);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 6px 16px;
    display: flex;
    gap: 20px;
    font-family: 'Space Mono', monospace;
    font-size: 10px;
    color: rgba(255,255,255,0.4);
    pointer-events: none;
    white-space: nowrap;
  }}
  #stats-bar span b {{ color: rgba(255,255,255,0.75); }}

  /* ── Zoom controls ───────────────────────────────────────────────────────── */
  #zoom-controls {{
    position: absolute;
    bottom: 60px;
    right: 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}
  .zoom-btn {{
    width: 32px;
    height: 32px;
    background: rgba(20,20,32,0.88);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    color: #e8e8f0;
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }}
  .zoom-btn:hover {{
    border-color: rgba(255,255,255,0.35);
    background: rgba(40,40,60,0.9);
  }}
</style>
</head>
<body>
<div id="container">

  <!-- ── Graph area ──────────────────────────────────────────────────────── -->
  <div id="sigma-container">

    <!-- Isolation banner (top of graph) -->
    <div id="isolation-banner">
      <span id="isolation-text">Modo aislamiento</span>
      <button id="isolation-exit">Salir ×</button>
    </div>

    <!-- Toolbar -->
    <div id="toolbar">
      <input id="search-box" type="text" placeholder="🔍  Buscar usuario..."/>

      <!-- Row 1: node-type filters + reset -->
      <div class="filter-row" id="type-filter-row">
        <button class="filter-btn active" data-filter="all">Todos</button>
        <button class="filter-btn" data-filter="course">Solo curso</button>
        <button class="filter-btn" data-filter="mutual">Mutuos</button>
        <button class="filter-btn" id="reset-btn">↺ Reset</button>
      </div>

      <!-- Row 2: community filters (populated by JS) -->
      <div class="filter-row" id="community-filter-row"></div>
    </div>

    <!-- Zoom controls -->
    <div id="zoom-controls">
      <button class="zoom-btn" id="zoom-in">+</button>
      <button class="zoom-btn" id="zoom-out">−</button>
      <button class="zoom-btn" id="zoom-fit" title="Ajustar">⊡</button>
    </div>

    <!-- Stats bar -->
    <div id="stats-bar">
      <span><b id="stat-nodes">0</b> nodos</span>
      <span><b id="stat-edges">0</b> arcos</span>
      <span><b id="stat-communities">0</b> comunidades</span>
      <span><b id="stat-density">0</b> densidad</span>
    </div>
  </div>

  <!-- ── Side panel ──────────────────────────────────────────────────────── -->
  <div id="panel">
    <button id="panel-close">×</button>
    <div id="panel-inner">
      <div class="panel-username" id="p-username">username</div>
      <div id="p-badge" class="panel-badge badge-external">EXTERNO</div>

      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Seguidores</div>
          <div class="metric-value" id="p-indegree">0</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Siguiendo</div>
          <div class="metric-value" id="p-outdegree">0</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Mutuos</div>
          <div class="metric-value" id="p-mutual">0</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Comunidad</div>
          <div class="metric-value" id="p-community">—</div>
        </div>
      </div>

      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Betweenness</div>
          <div class="metric-value small" id="p-betweenness">0</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">PageRank</div>
          <div class="metric-value small" id="p-pagerank">0</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Closeness</div>
          <div class="metric-value small" id="p-closeness">0</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Clustering</div>
          <div class="metric-value small" id="p-clustering">0</div>
        </div>
      </div>

      <!-- Isolation action buttons -->
      <div class="panel-action-row">
        <button class="panel-action-btn" id="btn-isolate-neighbors">⬡ Aislar vecinos</button>
        <button class="panel-action-btn" id="btn-isolate-community">⬡ Ver comunidad</button>
      </div>

      <hr class="divider"/>

      <div id="follows-section">
        <div class="section-title">Sigue a (<span id="p-follows-count">0</span>)</div>
        <div class="node-list" id="p-follows"></div>
      </div>

      <div id="followed-section">
        <div class="section-title">Seguido por (<span id="p-followers-count">0</span>)</div>
        <div class="node-list" id="p-followers"></div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/graphology/0.25.4/graphology.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/sigma.js/2.4.0/sigma.min.js"></script>
<script>
const GRAPH_DATA = {graph_str};

const COMMUNITY_COLORS = [
  "#e63946","#457b9d","#2a9d8f","#e9c46a","#f4a261",
  "#a8dadc","#6a4c93","#1982c4","#8ac926","#ff595e",
  "#ffca3a","#6a994e","#bc4749","#0077b6","#7b2d8b"
];

// ── Build graphology graph ─────────────────────────────────────────────────
const graph = new graphology.Graph({{ type: 'directed', multi: false }});

GRAPH_DATA.nodes.forEach(n => {{
  graph.addNode(n.id, {{
    label: n.label,
    x: n.x,
    y: n.y,
    size: n.size,
    color: n.color,
    has_file: n.has_file,
    is_anonymous: n.is_anonymous || false,
    in_degree: n.in_degree,
    out_degree: n.out_degree,
    betweenness: n.betweenness,
    closeness: n.closeness,
    clustering: n.clustering,
    pagerank: n.pagerank,
    mutual_count: n.mutual_count,
    community: n.community,
    originalColor: n.color,
    originalSize: n.size,
  }});
}});

GRAPH_DATA.edges.forEach(e => {{
  try {{
    graph.addEdge(e.source, e.target, {{
      id: e.id,
      size: 1,
      color: "rgba(255,255,255,0.06)",
      originalColor: "rgba(255,255,255,0.06)",
      timestamp: e.timestamp,
    }});
  }} catch(err) {{}}
}});

// ── Sigma renderer ─────────────────────────────────────────────────────────
const renderer = new Sigma(graph, document.getElementById("sigma-container"), {{
  renderEdgeLabels: false,
  defaultEdgeColor: "rgba(255,255,255,0.03)",
  defaultNodeColor: "#7c6fff",
  labelFont: "Space Mono, monospace",
  labelSize: 11,
  labelColor: {{ color: "rgba(255,255,255,0.8)" }},
  edgeReducer: (edge, data) => ({{ 
    ...data, 
    size: 0.5,
    color: data.hidden ? "transparent" : (data.color || "rgba(255,255,255,0.03)")
  }}),
  nodeReducer: (node, data) => {{
    const res = {{ ...data }};
    if (res.hidden) return {{ ...res, label: "" }};

    // Solo mostrar label si es owner, tiene PageRank alto, o está seleccionado/hover
    const isImportant = data.has_file || data.pagerank > 0.01;
    const isHovered = node === hoveredNode;
    const isSelected = node === selectedNode;

    if (!isImportant && !isHovered && !isSelected) {{
      res.label = "";
    }}
    return res;
  }},
}});

let hoveredNode = null;
renderer.on("enterNode", ({{ node }}) => {{
  hoveredNode = node;
  if (!selectedNode) highlightNode(node);
}});
renderer.on("leaveNode", () => {{
  hoveredNode = null;
  if (!selectedNode) resetHighlight();
}});

// Zoom inicial más alejado
renderer.getCamera().setState({{ ratio: 1.2 }});
const allCommunities = new Set(GRAPH_DATA.nodes.map(n => n.community));
const density = GRAPH_DATA.nodes.length > 1
  ? (GRAPH_DATA.edges.length / (GRAPH_DATA.nodes.length * (GRAPH_DATA.nodes.length - 1))).toFixed(4)
  : 0;

document.getElementById("stat-nodes").textContent = GRAPH_DATA.nodes.length;
document.getElementById("stat-edges").textContent = GRAPH_DATA.edges.length;
document.getElementById("stat-communities").textContent = allCommunities.size;
document.getElementById("stat-density").textContent = density;

// ── State ──────────────────────────────────────────────────────────────────
let selectedNode = null;
let activeFilter = "all";       // "all" | "course" | "mutual"
let activeCommunities = new Set();  // Set of community IDs to show
let isolationMode = null;       // null | "neighbors" | "community"
let isolatedNodes = new Set();  // nodes visible in isolation
let hiddenNodes = new Set();

// ── Community filter buttons (dynamic) ────────────────────────────────────
const communityIds = [...allCommunities].sort((a, b) => a - b);
const commRow = document.getElementById("community-filter-row");

communityIds.forEach(cid => {{
  const color = COMMUNITY_COLORS[cid % COMMUNITY_COLORS.length];
  const btn = document.createElement("button");
  btn.className = "filter-btn comm-btn";
  btn.textContent = "C" + cid;
  btn.dataset.community = String(cid);
  btn.style.borderLeftColor = color;

  btn.addEventListener("click", () => {{
    if (activeCommunities.has(cid)) {{
      activeCommunities.delete(cid);
      btn.classList.remove("active");
      btn.style.background = "";
      btn.style.color = "";
    }} else {{
      activeCommunities.add(cid);
      btn.classList.add("active");
      btn.style.background = color + "33";
      btn.style.color = color;
    }}
    exitIsolation(false);
    applyFilter();
  }});

  commRow.appendChild(btn);
}});

// ── Reset button ───────────────────────────────────────────────────────────
document.getElementById("reset-btn").addEventListener("click", () => {{
  activeFilter = "all";
  activeCommunities.clear();

  document.querySelectorAll(".filter-btn[data-filter]").forEach(b => {{
    b.classList.toggle("active", b.dataset.filter === "all");
  }});
  document.querySelectorAll(".comm-btn").forEach(b => {{
    b.classList.remove("active");
    b.style.background = "";
    b.style.color = "";
  }});

  exitIsolation(true);
}});

// ── Isolation banner ───────────────────────────────────────────────────────
const isolationBanner = document.getElementById("isolation-banner");

document.getElementById("isolation-exit").onclick = () => {{
  exitIsolation(true);
}};

function exitIsolation(andApplyFilter) {{
  isolationMode = null;
  isolatedNodes.clear();
  isolationBanner.classList.remove("visible");
  document.getElementById("btn-isolate-neighbors").classList.remove("active");
  document.getElementById("btn-isolate-community").classList.remove("active");
  if (andApplyFilter) applyFilter();
}}

// ── Panel ──────────────────────────────────────────────────────────────────
const panel = document.getElementById("panel");

function openPanel(nodeId) {{
  const attrs = graph.getNodeAttributes(nodeId);
  selectedNode = nodeId;

  document.getElementById("p-username").textContent = nodeId;

  const badge = document.getElementById("p-badge");
  if (attrs.is_anonymous) {{
    badge.textContent = "ANON";
    badge.className = "panel-badge badge-anon";
  }} else if (attrs.has_file) {{
    badge.textContent = "CURSO";
    badge.className = "panel-badge badge-course";
  }} else {{
    badge.textContent = "EXTERNO";
    badge.className = "panel-badge badge-external";
  }}

  document.getElementById("p-indegree").textContent = attrs.in_degree;
  document.getElementById("p-outdegree").textContent = attrs.out_degree;
  document.getElementById("p-mutual").textContent = attrs.mutual_count;
  document.getElementById("p-community").textContent = attrs.community;
  document.getElementById("p-betweenness").textContent = attrs.betweenness?.toFixed(4) ?? "—";
  document.getElementById("p-pagerank").textContent = attrs.pagerank?.toFixed(6) ?? "—";
  document.getElementById("p-closeness").textContent = attrs.closeness?.toFixed(4) ?? "—";
  document.getElementById("p-clustering").textContent = attrs.clustering?.toFixed(4) ?? "—";

  const followsOut = graph.outNeighbors(nodeId);
  document.getElementById("p-follows-count").textContent = followsOut.length;
  const followsEl = document.getElementById("p-follows");
  followsEl.innerHTML = "";
  followsOut.slice(0, 50).forEach(u => {{
    const chip = document.createElement("div");
    chip.className = "node-chip";
    chip.textContent = "@" + u;
    chip.onclick = () => focusNode(u);
    followsEl.appendChild(chip);
  }});

  const followsIn = graph.inNeighbors(nodeId);
  document.getElementById("p-followers-count").textContent = followsIn.length;
  const followersEl = document.getElementById("p-followers");
  followersEl.innerHTML = "";
  followsIn.slice(0, 50).forEach(u => {{
    const chip = document.createElement("div");
    chip.className = "node-chip";
    chip.textContent = "@" + u;
    chip.onclick = () => focusNode(u);
    followersEl.appendChild(chip);
  }});

  panel.classList.add("open");
  highlightNode(nodeId);
}}

function closePanel() {{
  panel.classList.remove("open");
  selectedNode = null;
  exitIsolation(true);
  resetHighlight();
}}

document.getElementById("panel-close").onclick = closePanel;

// ── Isolation buttons (inside panel) ──────────────────────────────────────
document.getElementById("btn-isolate-neighbors").onclick = () => {{
  if (!selectedNode) return;
  if (isolationMode === "neighbors") {{
    exitIsolation(true);
    return;
  }}
  isolationMode = "neighbors";
  isolatedNodes = new Set([
    selectedNode,
    ...graph.outNeighbors(selectedNode),
    ...graph.inNeighbors(selectedNode),
  ]);
  document.getElementById("isolation-text").textContent =
    "Vecinos de @" + selectedNode + " — " + (isolatedNodes.size - 1) + " conexiones";
  isolationBanner.classList.add("visible");
  document.getElementById("btn-isolate-neighbors").classList.add("active");
  document.getElementById("btn-isolate-community").classList.remove("active");
  applyFilter();
}};

document.getElementById("btn-isolate-community").onclick = () => {{
  if (!selectedNode) return;
  if (isolationMode === "community") {{
    exitIsolation(true);
    return;
  }}
  const comm = graph.getNodeAttribute(selectedNode, "community");
  isolationMode = "community";
  isolatedNodes = new Set(
    graph.nodes().filter(n => graph.getNodeAttribute(n, "community") === comm)
  );
  document.getElementById("isolation-text").textContent =
    "Comunidad " + comm + " — " + isolatedNodes.size + " nodos";
  isolationBanner.classList.add("visible");
  document.getElementById("btn-isolate-community").classList.add("active");
  document.getElementById("btn-isolate-neighbors").classList.remove("active");
  applyFilter();
}};

// ── Apply filter ───────────────────────────────────────────────────────────
function applyFilter() {{
  hiddenNodes.clear();

  graph.forEachNode((n, attrs) => {{
    let hidden = false;

    // Node-type filter
    if (activeFilter === "course" && !attrs.has_file) hidden = true;
    if (activeFilter === "mutual" && attrs.mutual_count === 0) hidden = true;

    // Community filter (stacks on top)
    if (activeCommunities.size > 0 && !activeCommunities.has(attrs.community)) hidden = true;

    // Isolation mode (overrides all — only show isolated nodes)
    if (isolationMode && !isolatedNodes.has(n)) hidden = true;

    graph.setNodeAttribute(n, "hidden", hidden);
    if (hidden) hiddenNodes.add(n);
  }});

  graph.forEachEdge((edge, attrs, source, target) => {{
    graph.setEdgeAttribute(edge, "hidden",
      hiddenNodes.has(source) || hiddenNodes.has(target));
  }});

  if (selectedNode && hiddenNodes.has(selectedNode)) closePanel();
}}

// ── Highlight ──────────────────────────────────────────────────────────────
function highlightNode(nodeId) {{
  const neighbors = new Set([
    ...graph.outNeighbors(nodeId),
    ...graph.inNeighbors(nodeId),
  ]);

  graph.forEachNode((n, attrs) => {{
    if (hiddenNodes.has(n)) return;
    if (n === nodeId) {{
      graph.setNodeAttribute(n, "color", "#ffffff");
      graph.setNodeAttribute(n, "size", attrs.originalSize * 1.6);
    }} else if (neighbors.has(n)) {{
      graph.setNodeAttribute(n, "color", attrs.originalColor);
      graph.setNodeAttribute(n, "size", attrs.originalSize);
    }} else {{
      graph.setNodeAttribute(n, "color", "rgba(255,255,255,0.06)");
      graph.setNodeAttribute(n, "size", attrs.originalSize * 0.6);
    }}
  }});

  graph.forEachEdge((edge, attrs, source, target) => {{
    if (hiddenNodes.has(source) || hiddenNodes.has(target)) return;
    if (source === nodeId || target === nodeId) {{
      graph.setEdgeAttribute(edge, "color", source === nodeId ? "#7c6fff" : "#e63946");
      graph.setEdgeAttribute(edge, "size", 2);
    }} else {{
      graph.setEdgeAttribute(edge, "color", "rgba(255,255,255,0.02)");
      graph.setEdgeAttribute(edge, "size", 0.5);
    }}
  }});
}}

function resetHighlight() {{
  graph.forEachNode((n, attrs) => {{
    if (!hiddenNodes.has(n)) {{
      graph.setNodeAttribute(n, "color", attrs.originalColor);
      graph.setNodeAttribute(n, "size", attrs.originalSize);
    }}
  }});
  graph.forEachEdge((edge, attrs, source, target) => {{
    if (!hiddenNodes.has(source) && !hiddenNodes.has(target)) {{
      graph.setEdgeAttribute(edge, "color", "rgba(255,255,255,0.06)");
      graph.setEdgeAttribute(edge, "size", 1);
    }}
  }});
}}

// ── Sigma events ───────────────────────────────────────────────────────────
renderer.on("clickNode", ({{ node }}) => {{
  if (selectedNode === node) closePanel();
  else openPanel(node);
}});

renderer.on("clickStage", () => {{
  if (selectedNode) closePanel();
}});

renderer.on("enterNode", ({{ node }}) => {{
  if (!selectedNode) highlightNode(node);
}});

renderer.on("leaveNode", () => {{
  if (!selectedNode) resetHighlight();
}});

// ── Focus node ─────────────────────────────────────────────────────────────
function focusNode(nodeId) {{
  if (!graph.hasNode(nodeId)) return;
  const attrs = graph.getNodeAttributes(nodeId);
  renderer.getCamera().animate(
    {{ x: attrs.x, y: attrs.y, ratio: 0.5 }},
    {{ duration: 500 }}
  );
  openPanel(nodeId);
}}

// ── Search ─────────────────────────────────────────────────────────────────
document.getElementById("search-box").addEventListener("input", e => {{
  const query = e.target.value.toLowerCase().trim();
  if (!query) {{ resetHighlight(); return; }}
  const match = graph.nodes().find(n => n.toLowerCase().includes(query));
  if (match) focusNode(match);
}});

// ── Node-type filter buttons ───────────────────────────────────────────────
document.querySelectorAll(".filter-btn[data-filter]").forEach(btn => {{
  btn.addEventListener("click", () => {{
    document.querySelectorAll(".filter-btn[data-filter]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeFilter = btn.dataset.filter;
    exitIsolation(false);
    applyFilter();
  }});
}});

// ── Zoom controls ──────────────────────────────────────────────────────────
document.getElementById("zoom-in").onclick  = () => renderer.getCamera().animatedZoom({{ duration: 300 }});
document.getElementById("zoom-out").onclick = () => renderer.getCamera().animatedUnzoom({{ duration: 300 }});
document.getElementById("zoom-fit").onclick = () => renderer.getCamera().animatedReset({{ duration: 300 }});
</script>
</body>
</html>"""
    return html
