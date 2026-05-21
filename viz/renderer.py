"""
viz/renderer.py
---------------
Genera el HTML del componente Sigma.js para embeber en Streamlit.
"""

import json

# Debe coincidir con COMMUNITY_COLORS en graph_builder.py
COMMUNITY_COLORS = [
    "#e63946", "#f4a261", "#2a9d8f", "#e9c46a", "#a8dadc",
    "#6a4c93", "#8ac926", "#ff595e", "#ffca3a", "#6a994e",
    "#bc4749", "#0077b6", "#7b2d8b", "#457b9d", "#1982c4",
]

OWNER_COLORS = [
    "#ff6b9d", "#c77dff", "#4cc9f0", "#f72585", "#7209b7",
    "#3a0ca3", "#4361ee", "#4895ef", "#43aa8b", "#90be6d",
    "#f9c74f", "#f8961e",
]

COURSE_COLOR = "#4e9af1"


def build_sigma_html(graph_json: dict, height: int = 700) -> str:
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

  /* ── Toolbar ── */
  #toolbar {{
    position: absolute;
    top: 16px;
    left: 16px;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 480px;
  }}
  #search-box {{
    background: rgba(20,20,32,0.92);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px;
    padding: 8px 12px;
    color: #e8e8f0;
    font-family: 'Space Mono', monospace;
    font-size: 12px;
    width: 220px;
    outline: none;
    transition: border-color 0.2s;
  }}
  #search-box:focus {{ border-color: rgba(255,255,255,0.35); }}
  #search-box::placeholder {{ color: rgba(255,255,255,0.3); }}
  #search-hint {{
    display: none;
    font-size: 10px;
    font-family: 'Space Mono', monospace;
    color: rgba(255,255,255,0.4);
    padding: 2px 4px;
  }}
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
  .filter-btn:hover {{ border-color: rgba(255,255,255,0.35); background: rgba(40,40,60,0.9); }}
  .filter-btn.active {{ border-color: #7c6fff; background: rgba(124,111,255,0.2); color: #b8b0ff; }}
  .comm-btn {{ border-left-width: 3px !important; border-left-style: solid !important; padding-left: 8px !important; }}
  #reset-btn {{ opacity: 0.65; }}
  #reset-btn:hover {{ opacity: 1; }}

  /* Separador de sección en toolbar */
  .toolbar-label {{
    font-size: 9px;
    font-family: 'Space Mono', monospace;
    color: rgba(255,255,255,0.25);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 2px 0;
  }}

  /* ── Isolation banner ── */
  #isolation-banner {{
    display: none;
    position: absolute;
    top: 0; left: 0; right: 0;
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
  #isolation-banner.visible {{ display: flex; }}
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
  #isolation-exit:hover {{ background: rgba(124,111,255,0.2); }}

  /* ── Panel lateral ── */
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
    top: 12px; right: 12px;
    background: none; border: none;
    color: rgba(255,255,255,0.4);
    cursor: pointer; font-size: 18px; line-height: 1;
    padding: 4px; transition: color 0.15s; z-index: 2;
  }}
  #panel-close:hover {{ color: #e8e8f0; }}
  .panel-username {{
    font-family: 'Space Mono', monospace;
    font-size: 15px; font-weight: 700; color: #fff;
    margin-bottom: 4px; word-break: break-all;
  }}
  .panel-username::before {{ content: '@'; color: #7c6fff; }}
  .panel-badge {{
    display: inline-block;
    font-size: 9px; font-family: 'Space Mono', monospace;
    padding: 2px 7px; border-radius: 4px; margin-bottom: 16px;
    font-weight: 700; letter-spacing: 0.05em;
  }}
  .badge-course   {{ background: rgba(124,111,255,0.2); color: #b8b0ff; border: 1px solid rgba(124,111,255,0.4); }}
  .badge-external {{ background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.4); border: 1px solid rgba(255,255,255,0.1); }}
  .badge-anon     {{ background: rgba(255,200,0,0.1); color: #ffd166; border: 1px solid rgba(255,209,102,0.3); }}
  .metric-grid {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 8px; margin-bottom: 16px;
  }}
  .metric-card {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 8px; padding: 10px 12px;
  }}
  .metric-label {{
    font-size: 9px; font-family: 'Space Mono', monospace;
    color: rgba(255,255,255,0.35); text-transform: uppercase;
    letter-spacing: 0.08em; margin-bottom: 4px;
  }}
  .metric-value {{
    font-size: 18px; font-family: 'Space Mono', monospace;
    font-weight: 700; color: #e8e8f0;
  }}
  .metric-value.small {{ font-size: 13px; }}
  .panel-action-row {{
    display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px;
  }}
  .panel-action-btn {{
    width: 100%;
    background: rgba(20,20,32,0.88);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px; color: #e8e8f0;
    font-family: 'Space Mono', monospace; font-size: 10px;
    padding: 7px 10px; cursor: pointer; transition: all 0.15s; text-align: left;
  }}
  .panel-action-btn:hover {{ border-color: rgba(255,255,255,0.35); background: rgba(40,40,60,0.9); }}
  .panel-action-btn.active {{ border-color: #7c6fff; background: rgba(124,111,255,0.2); color: #b8b0ff; }}
  .section-title {{
    font-size: 9px; font-family: 'Space Mono', monospace;
    color: rgba(255,255,255,0.3); text-transform: uppercase;
    letter-spacing: 0.1em; margin-bottom: 10px;
  }}
  .node-list {{
    display: flex; flex-direction: column; gap: 4px;
    margin-bottom: 20px; max-height: 140px; overflow-y: auto;
  }}
  .node-list::-webkit-scrollbar {{ width: 3px; }}
  .node-list::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.1); border-radius: 2px; }}
  .node-chip {{
    font-family: 'Space Mono', monospace; font-size: 10px;
    color: rgba(255,255,255,0.6); padding: 4px 8px;
    background: rgba(255,255,255,0.04); border-radius: 4px;
    cursor: pointer; transition: all 0.15s;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .node-chip:hover {{ background: rgba(124,111,255,0.15); color: #b8b0ff; }}
  .divider {{ border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 14px 0; }}

  /* ── Stats bar ── */
  #stats-bar {{
    position: absolute; bottom: 12px; left: 50%; transform: translateX(-50%);
    background: rgba(10,10,20,0.85);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px; padding: 6px 16px;
    display: flex; gap: 20px;
    font-family: 'Space Mono', monospace; font-size: 10px;
    color: rgba(255,255,255,0.4);
    pointer-events: none; white-space: nowrap;
  }}
  #stats-bar span b {{ color: rgba(255,255,255,0.75); }}

  /* ── Zoom ── */
  #zoom-controls {{
    position: absolute; bottom: 60px; right: 16px;
    display: flex; flex-direction: column; gap: 4px;
  }}
  .zoom-btn {{
    width: 32px; height: 32px;
    background: rgba(20,20,32,0.88);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px; color: #e8e8f0; font-size: 16px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    transition: all 0.15s;
  }}
  .zoom-btn:hover {{ border-color: rgba(255,255,255,0.35); background: rgba(40,40,60,0.9); }}
</style>
</head>
<body>
<div id="container">
  <div id="sigma-container">
    <div id="isolation-banner">
      <span id="isolation-text">Modo aislamiento</span>
      <button id="isolation-exit">Salir ×</button>
    </div>

    <div id="toolbar">
      <input id="search-box" type="text" placeholder="🔍  Buscar usuario..."/>
      <div id="search-hint"></div>

      <div class="filter-row">
        <span class="toolbar-label">Vista:</span>
        <button class="filter-btn active" data-view="structural">Comunidades</button>
        <button class="filter-btn" data-view="owner">Por estudiante</button>
      </div>

      <div class="filter-row" id="type-filter-row">
        <span class="toolbar-label">Filtro:</span>
        <button class="filter-btn active" data-filter="all">Todos</button>
        <button class="filter-btn" data-filter="course">Solo curso</button>
        <button class="filter-btn" data-filter="mutual">Mutuos</button>
        <button class="filter-btn" id="reset-btn">↺ Reset</button>
      </div>

      <div class="filter-row" id="community-filter-row"></div>
    </div>

    <div id="zoom-controls">
      <button class="zoom-btn" id="zoom-in">+</button>
      <button class="zoom-btn" id="zoom-out">−</button>
      <button class="zoom-btn" id="zoom-fit" title="Ajustar">⊡</button>
    </div>

    <div id="stats-bar">
      <span><b id="stat-nodes">0</b> nodos</span>
      <span><b id="stat-edges">0</b> arcos</span>
      <span><b id="stat-communities">0</b> comunidades</span>
      <span><b id="stat-density">0</b> densidad</span>
    </div>
  </div>

  <div id="panel">
    <button id="panel-close">×</button>
    <div id="panel-inner">
      <div class="panel-username" id="p-username">username</div>
      <div id="p-badge" class="panel-badge badge-external">EXTERNO</div>
      <div class="metric-grid">
        <div class="metric-card"><div class="metric-label">Seguidores</div><div class="metric-value" id="p-indegree">0</div></div>
        <div class="metric-card"><div class="metric-label">Siguiendo</div><div class="metric-value" id="p-outdegree">0</div></div>
        <div class="metric-card"><div class="metric-label">Mutuos</div><div class="metric-value" id="p-mutual">0</div></div>
        <div class="metric-card"><div class="metric-label">Comunidad</div><div class="metric-value" id="p-community">—</div></div>
      </div>
      <div class="metric-grid">
        <div class="metric-card"><div class="metric-label">Betweenness</div><div class="metric-value small" id="p-betweenness">0</div></div>
        <div class="metric-card"><div class="metric-label">PageRank</div><div class="metric-value small" id="p-pagerank">0</div></div>
        <div class="metric-card"><div class="metric-label">Closeness</div><div class="metric-value small" id="p-closeness">0</div></div>
        <div class="metric-card"><div class="metric-label">Clustering</div><div class="metric-value small" id="p-clustering">0</div></div>
      </div>
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
const COMMUNITY_COLORS = {json.dumps(COMMUNITY_COLORS)};
const OWNER_COLORS     = {json.dumps(OWNER_COLORS)};
const COURSE_COLOR     = "{COURSE_COLOR}";

// ── Estado ────────────────────────────────────────────────────────────────────
let hoveredNode    = null;
let selectedNode   = null;
let activeFilter   = "all";
let activeView     = "structural";  // "structural" | "owner"
let activeCommunities = new Set();
let isolationMode  = null;
let isolatedNodes  = new Set();
let hiddenNodes    = new Set();

// Cache de vecinos para evitar recalcular en cada frame del nodeReducer
let neighborCache  = null;

// Flag anti-recursión: evita que closePanel → exitIsolation → applyFilter
// vuelva a llamar closePanel si selectedNode quedó en hiddenNodes
let _applyingFilter = false;

function buildNeighborCache(nodeId) {{
  if (!nodeId) {{ neighborCache = null; return; }}
  neighborCache = new Set([
    ...graph.outNeighbors(nodeId),
    ...graph.inNeighbors(nodeId),
  ]);
}}

// ── Grafo ─────────────────────────────────────────────────────────────────────
const graph = new graphology.Graph({{ type: 'directed', multi: false }});
// COORD_SCALE=1 porque graph_builder ya produce coordenadas amplias
const COORD_SCALE = 1.0;
GRAPH_DATA.nodes.forEach(n => {{
  graph.addNode(n.id, {{
    ...n,
    x: n.x * COORD_SCALE,
    y: n.y * COORD_SCALE,
    originalColor:      n.color,
    originalOwnerColor: n.owner_color,
    originalSize:       n.size * 0.8,
    size:               n.size * 0.8,
  }});
}});
GRAPH_DATA.edges.forEach(e => {{
  try {{
    // Preservar el color semántico calculado en el backend (puentes vs externos)
    const edgeColor = e.color || "rgba(255,255,255,0.015)";
    const edgeSize  = (e.edge_type === "course_to_course")    ? 1.4
                    : (e.edge_type === "bridge_to_course")    ? 0.7
                    : (e.edge_type === "course_to_external")  ? 0.5
                    : (e.edge_type === "bridge_to_bridge")    ? 0.2
                    : 0.08;
    graph.addEdge(e.source, e.target, {{
      ...e,
      size:          edgeSize,
      color:         edgeColor,
      originalColor: edgeColor,
    }});
  }} catch(err) {{}}
}});

// ── Renderer ──────────────────────────────────────────────────────────────────
const renderer = new Sigma(graph, document.getElementById("sigma-container"), {{
  renderEdgeLabels: false,
  defaultEdgeColor: "rgba(255,255,255,0.015)",
  labelFont: "Space Mono, monospace",
  labelSize: 11,
  labelColor: {{ color: "rgba(255,255,255,0.8)" }},
  // LOD: hide labels below this zoom ratio to reduce clutter
  labelRenderedSizeThreshold: 6,
  // Skip rendering tiny nodes when zoomed out (performance)
  nodeProgramClasses: {{}},
  edgeReducer: (edge, data) => {{
    const res = {{ ...data }};
    const src = graph.source(edge);
    const tgt = graph.target(edge);
    if (hiddenNodes.has(src) || hiddenNodes.has(tgt)) {{
      res.hidden = true;
      return res;
    }}
    res.hidden = false;
    if (selectedNode) {{
      if (src === selectedNode || tgt === selectedNode) {{
        res.color = src === selectedNode ? "#7c6fff" : "#e63946";
        res.size  = 2.5;
      }} else {{
        res.hidden = true;
      }}
    }} else if (hoveredNode) {{
      if (src === hoveredNode || tgt === hoveredNode) {{
        res.color = src === hoveredNode ? "#7c6fff" : "#e63946";
        res.size  = 1.5;
      }} else {{
        res.color = "rgba(255,255,255,0.006)";
        res.size  = 0.05;
      }}
    }} else {{
      res.color = data.originalColor || "rgba(255,255,255,0.015)";
      res.size  = data.size || 0.1;
    }}
    return res;
  }},
  nodeReducer: (node, data) => {{
    const res = {{ ...data }};
    if (hiddenNodes.has(node)) {{
      res.hidden = true;
      res.label  = "";
      return res;
    }}
    res.hidden = false;

    // Dim non-neighbors when a node is selected (use cached set)
    if (selectedNode && node !== selectedNode) {{
      if (!neighborCache || !neighborCache.has(node)) {{
        res.color = "rgba(30,30,50,0.18)";
        res.label = "";
        res.size  = data.originalSize * 0.35;
        return res;
      }}
    }}

    // Course nodes: always labelled with white border ring
    if (data.has_file) {{
      res.label       = node;
      res.borderColor = "#ffffff";
      res.borderSize  = 0.3;
      res.highlighted = true;
      return res;
    }}

    // Bridge nodes: subtle ring, label only when important
    if (data.is_bridge) {{
      res.borderColor = data.originalColor;
      res.borderSize  = 0.12;
      if (node === hoveredNode || node === selectedNode || data.pagerank > 0.015) {{
        res.label = node;
      }} else {{
        res.label = "";
      }}
      return res;
    }}

    // External nodes: label only at high pagerank
    if (data.pagerank <= 0.02 && node !== hoveredNode && node !== selectedNode) {{
      res.label = "";
    }}
    return res;
  }},
}});

// ── Aplicar vista (structural / owner) ───────────────────────────────────────
function applyView(view) {{
  activeView = view;
  graph.forEachNode((n, attrs) => {{
    const col = view === "owner" ? attrs.originalOwnerColor : attrs.originalColor;
    graph.setNodeAttribute(n, "originalColor", col);
    // Solo actualizar color visible si no está resaltado
    if (n !== selectedNode && n !== hoveredNode) {{
      graph.setNodeAttribute(n, "color", col);
    }}
  }});

  // Actualizar botones de vista
  document.querySelectorAll(".filter-btn[data-view]").forEach(b => {{
    b.classList.toggle("active", b.dataset.view === view);
  }});

  // Regenerar botones de comunidad/owner según la vista activa
  rebuildGroupButtons();
  renderer.refresh();
}}

// ── Botones de grupo (comunidad o owner) ──────────────────────────────────────
function rebuildGroupButtons() {{
  const commRow = document.getElementById("community-filter-row");
  commRow.innerHTML = "";
  activeCommunities.clear();

  if (activeView === "structural") {{
    const communities = [...new Set(GRAPH_DATA.nodes.map(n => n.community))].sort((a,b)=>a-b);
    communities.forEach(cid => {{
      const sample = GRAPH_DATA.nodes.find(n => n.community === cid && !n.has_file);
      const color  = sample ? sample.color : COMMUNITY_COLORS[cid % COMMUNITY_COLORS.length];
      const btn    = document.createElement("button");
      btn.className = "filter-btn comm-btn";
      btn.textContent = "C" + cid;
      btn.style.borderLeftColor = color;
      btn.dataset.gid = cid;
      btn.onclick = () => toggleGroupBtn(btn, cid, "community");
      commRow.appendChild(btn);
    }});
  }} else {{
    // Vista por owner: un botón por estudiante
    const owners = [...new Set(GRAPH_DATA.nodes
      .filter(n => n.has_file)
      .map(n => n.owner_group))].sort((a,b)=>a-b);
    // Construir mapa owner_group → username del curso
    const ownerNames = {{}};
    GRAPH_DATA.nodes.filter(n => n.has_file).forEach(n => {{
      ownerNames[n.owner_group] = n.id;
    }});
    owners.forEach(oid => {{
      const color = OWNER_COLORS[oid % OWNER_COLORS.length];
      const btn   = document.createElement("button");
      btn.className = "filter-btn comm-btn";
      btn.textContent = ownerNames[oid] ? "@" + ownerNames[oid].slice(0,12) : "S" + oid;
      btn.style.borderLeftColor = color;
      btn.dataset.gid = oid;
      btn.onclick = () => toggleGroupBtn(btn, oid, "owner_group");
      commRow.appendChild(btn);
    }});
  }}
}}

function toggleGroupBtn(btn, gid, attr) {{
  if (activeCommunities.has(gid)) {{
    activeCommunities.delete(gid);
    btn.classList.remove("active");
    btn.style.background = "";
  }} else {{
    activeCommunities.add(gid);
    btn.classList.add("active");
    const color = btn.style.borderLeftColor;
    btn.style.background = color.replace("rgb", "rgba").replace(")", ",0.2)");
  }}
  exitIsolation(false);
  applyFilter();
}}

// ── Filtrado ──────────────────────────────────────────────────────────────────
function applyFilter() {{
  if (_applyingFilter) return;
  _applyingFilter = true;

  hiddenNodes.clear();

  const groupAttr = activeView === "owner" ? "owner_group" : "community";

  graph.forEachNode((n, attrs) => {{
    let hidden = false;
    if (activeFilter === "course"  && !attrs.has_file)           hidden = true;
    if (activeFilter === "mutual"  && attrs.mutual_count === 0)  hidden = true;
    if (activeCommunities.size > 0 && !activeCommunities.has(attrs[groupAttr])) hidden = true;
    if (isolationMode && !isolatedNodes.has(n))                  hidden = true;
    if (hidden) hiddenNodes.add(n);
  }});

  // Si el nodo seleccionado queda oculto, cerrar panel SIN recursión
  if (selectedNode && hiddenNodes.has(selectedNode)) {{
    _closePanelInternal();
  }}

  renderer.refresh();
  _applyingFilter = false;
}}

// Cierre interno de panel — no llama a exitIsolation para evitar recursión
function _closePanelInternal() {{
  document.getElementById("panel").classList.remove("open");
  selectedNode = null;
  neighborCache = null;
  resetHighlight();
}}

// ── Highlight ─────────────────────────────────────────────────────────────────
// highlightNode modifica atributos del grafo para persistir el estado al hacer
// click; el hover solo usa el reducer sin modificar atributos (más rápido).
function highlightNode(nodeId) {{
  const neighbors = neighborCache || new Set([...graph.outNeighbors(nodeId), ...graph.inNeighbors(nodeId)]);
  graph.forEachNode((n, attrs) => {{
    if (hiddenNodes.has(n)) return;
    if (n === nodeId) {{
      graph.setNodeAttribute(n, "color", "#ffffff");
      graph.setNodeAttribute(n, "size", attrs.originalSize * 1.8);
    }} else if (neighbors.has(n)) {{
      graph.setNodeAttribute(n, "color", attrs.originalColor);
      graph.setNodeAttribute(n, "size", attrs.originalSize * 1.1);
    }} else {{
      graph.setNodeAttribute(n, "color", "rgba(30,30,50,0.18)");
      graph.setNodeAttribute(n, "size",  attrs.originalSize * 0.35);
    }}
  }});
  renderer.refresh();
}}

function resetHighlight() {{
  graph.forEachNode((n, attrs) => {{
    if (!hiddenNodes.has(n)) {{
      graph.setNodeAttribute(n, "color", attrs.originalColor);
      graph.setNodeAttribute(n, "size",  attrs.originalSize);
    }}
  }});
  graph.forEachEdge((edge, attrs, source, target) => {{
    if (!hiddenNodes.has(source) && !hiddenNodes.has(target)) {{
      graph.setEdgeAttribute(edge, "color", attrs.originalColor || "rgba(255,255,255,0.015)");
      graph.setEdgeAttribute(edge, "size", attrs.size || 0.1);
    }}
  }});
}}

// ── Panel lateral ─────────────────────────────────────────────────────────────
const panel = document.getElementById("panel");

function openPanel(nodeId) {{
  const attrs = graph.getNodeAttributes(nodeId);
  selectedNode = nodeId;
  buildNeighborCache(nodeId);
  document.getElementById("p-username").textContent = nodeId;
  const badge = document.getElementById("p-badge");
  badge.textContent = attrs.is_anonymous ? "ANON" : (attrs.has_file ? "CURSO" : "EXTERNO");
  badge.className = "panel-badge " + (attrs.is_anonymous ? "badge-anon" : (attrs.has_file ? "badge-course" : "badge-external"));

  const mapping = {{
    indegree:    "in_degree",
    outdegree:   "out_degree",
    mutual:      "mutual_count",
    community:   "community",
    betweenness: "betweenness",
    pagerank:    "pagerank",
    closeness:   "closeness",
    clustering:  "clustering",
  }};
  Object.entries(mapping).forEach(([m, attr]) => {{
    const val = attrs[attr];
    const el  = document.getElementById("p-" + m);
    if (el) el.textContent = (typeof val === "number" && val < 1) ? val.toFixed(4) : (val ?? "—");
  }});

  const updateList = (id, neighbors) => {{
    const el = document.getElementById(id); el.innerHTML = "";
    neighbors.slice(0, 50).forEach(u => {{
      const chip = document.createElement("div"); chip.className = "node-chip"; chip.textContent = "@" + u;
      chip.onclick = () => focusNode(u); el.appendChild(chip);
    }});
  }};
  updateList("p-follows",   graph.outNeighbors(nodeId));
  updateList("p-followers", graph.inNeighbors(nodeId));
  document.getElementById("p-follows-count").textContent   = graph.outNeighbors(nodeId).length;
  document.getElementById("p-followers-count").textContent = graph.inNeighbors(nodeId).length;

  panel.classList.add("open");
  highlightNode(nodeId);
}}

function closePanel() {{
  panel.classList.remove("open");
  selectedNode = null;
  neighborCache = null;
  exitIsolation(true);
  resetHighlight();
}}
document.getElementById("panel-close").onclick = closePanel;

function focusNode(nodeId) {{
  if (!graph.hasNode(nodeId)) return;
  // Si el nodo está oculto por algún filtro, limpiar filtros primero
  if (hiddenNodes.has(nodeId)) {{
    activeFilter = "all";
    activeCommunities.clear();
    document.querySelectorAll(".filter-btn[data-filter]").forEach(b =>
      b.classList.toggle("active", b.dataset.filter === "all"));
    document.querySelectorAll(".comm-btn").forEach(b => {{
      b.classList.remove("active"); b.style.background = "";
    }});
    exitIsolation(false);
    applyFilter();
  }}
  const attrs = graph.getNodeAttributes(nodeId);
  renderer.getCamera().animate({{ x: attrs.x, y: attrs.y, ratio: 0.5 }}, {{ duration: 500 }});
  openPanel(nodeId);
}}

// ── Aislamiento ───────────────────────────────────────────────────────────────
function exitIsolation(andApplyFilter) {{
  isolationMode = null; isolatedNodes.clear();
  document.getElementById("isolation-banner").classList.remove("visible");
  document.getElementById("btn-isolate-neighbors").classList.remove("active");
  document.getElementById("btn-isolate-community").classList.remove("active");
  if (andApplyFilter) applyFilter();
}}

document.getElementById("isolation-exit").onclick = () => exitIsolation(true);

document.getElementById("btn-isolate-neighbors").onclick = () => {{
  if (!selectedNode) return;
  if (isolationMode === "neighbors") return exitIsolation(true);
  isolationMode  = "neighbors";
  isolatedNodes  = new Set([selectedNode, ...graph.outNeighbors(selectedNode), ...graph.inNeighbors(selectedNode)]);
  document.getElementById("isolation-text").textContent = "Vecinos de @" + selectedNode;
  document.getElementById("isolation-banner").classList.add("visible");
  document.getElementById("btn-isolate-neighbors").classList.add("active");
  applyFilter();
}};

document.getElementById("btn-isolate-community").onclick = () => {{
  if (!selectedNode) return;
  if (isolationMode === "community") return exitIsolation(true);
  const groupAttr = activeView === "owner" ? "owner_group" : "community";
  const comm = graph.getNodeAttribute(selectedNode, groupAttr);
  isolationMode = "community";
  isolatedNodes = new Set(graph.nodes().filter(n => graph.getNodeAttribute(n, groupAttr) === comm));
  document.getElementById("isolation-text").textContent = "Comunidad " + comm;
  document.getElementById("isolation-banner").classList.add("visible");
  document.getElementById("btn-isolate-community").classList.add("active");
  applyFilter();
}};

// ── Eventos del renderer ──────────────────────────────────────────────────────
renderer.on("enterNode", ({{ node }}) => {{
  hoveredNode = node;
  if (!selectedNode) {{
    buildNeighborCache(node);
    renderer.refresh();
  }}
}});
renderer.on("leaveNode", () => {{
  hoveredNode = null;
  if (!selectedNode) {{
    neighborCache = null;
    renderer.refresh();
  }}
}});
renderer.on("clickNode", ({{ node }}) => {{
  if (selectedNode === node) closePanel(); else openPanel(node);
}});
renderer.on("clickStage", () => {{
  if (selectedNode) closePanel();
}});

// ── Buscador ──────────────────────────────────────────────────────────────────
// Bug fix: el buscador anterior llamaba focusNode en cada pulsación de tecla,
// lo que provocaba que una búsqueda que no matcheaba nada dejara el estado
// corrupto. Ahora: busca solo al pulsar Enter o cuando la caja pierde foco,
// y mientras se escribe solo muestra un hint de cuántos coinciden.
let _searchTimeout = null;
const searchBox  = document.getElementById("search-box");
const searchHint = document.getElementById("search-hint");

searchBox.addEventListener("input", e => {{
  clearTimeout(_searchTimeout);
  const query = e.target.value.trim();
  if (!query) {{
    searchHint.style.display = "none";
    searchHint.textContent   = "";
    return;
  }}
  const q       = query.toLowerCase();
  const matches = graph.nodes().filter(n => n.toLowerCase().includes(q));
  if (matches.length === 0) {{
    searchHint.style.display  = "block";
    searchHint.textContent    = "Sin resultados";
  }} else if (matches.length === 1) {{
    searchHint.style.display  = "block";
    searchHint.textContent    = "↵ para ir a @" + matches[0];
    // Auto-navegar si es match exacto
    if (matches[0].toLowerCase() === q) {{
      _searchTimeout = setTimeout(() => focusNode(matches[0]), 300);
    }}
  }} else {{
    searchHint.style.display  = "block";
    searchHint.textContent    = matches.length + " coincidencias · ↵ para la primera";
  }}
}});

searchBox.addEventListener("keydown", e => {{
  if (e.key !== "Enter") return;
  const query = searchBox.value.trim().toLowerCase();
  if (!query) return;
  const match = graph.nodes().find(n => n.toLowerCase().includes(query));
  if (match) {{
    focusNode(match);
    searchHint.style.display = "none";
  }}
}});

searchBox.addEventListener("blur", () => {{
  // Pequeño delay para permitir clicks en chips del panel
  setTimeout(() => {{ searchHint.style.display = "none"; }}, 200);
}});

// ── Filtros de tipo ───────────────────────────────────────────────────────────
document.querySelectorAll(".filter-btn[data-filter]").forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll(".filter-btn[data-filter]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeFilter = btn.dataset.filter;
    exitIsolation(false);
    applyFilter();
  }};
}});

// ── Botones de vista ──────────────────────────────────────────────────────────
document.querySelectorAll(".filter-btn[data-view]").forEach(btn => {{
  btn.onclick = () => applyView(btn.dataset.view);
}});

// ── Reset ─────────────────────────────────────────────────────────────────────
document.getElementById("reset-btn").onclick = () => {{
  activeFilter = "all";
  activeCommunities.clear();
  document.querySelectorAll(".filter-btn[data-filter]").forEach(b =>
    b.classList.toggle("active", b.dataset.filter === "all"));
  document.querySelectorAll(".comm-btn").forEach(b => {{
    b.classList.remove("active"); b.style.background = "";
  }});
  exitIsolation(true);
}};

// ── Stats bar ─────────────────────────────────────────────────────────────────
const density = GRAPH_DATA.nodes.length > 1
  ? (GRAPH_DATA.edges.length / (GRAPH_DATA.nodes.length * (GRAPH_DATA.nodes.length - 1))).toFixed(4)
  : 0;
document.getElementById("stat-nodes").textContent       = GRAPH_DATA.nodes.length;
document.getElementById("stat-edges").textContent       = GRAPH_DATA.edges.length;
document.getElementById("stat-communities").textContent = new Set(GRAPH_DATA.nodes.map(n => n.community)).size;
document.getElementById("stat-density").textContent     = density;

// ── Zoom ──────────────────────────────────────────────────────────────────────
document.getElementById("zoom-in").onclick  = () => renderer.getCamera().animatedZoom();
document.getElementById("zoom-out").onclick = () => renderer.getCamera().animatedUnzoom();
document.getElementById("zoom-fit").onclick = () => renderer.getCamera().animatedReset();
renderer.getCamera().setState({{ ratio: 2.8 }});

// ── Init ──────────────────────────────────────────────────────────────────────
rebuildGroupButtons();
</script>
</body>
</html>"""
    return html
