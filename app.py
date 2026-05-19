"""
app.py
------
Aplicación Streamlit para análisis de grafo social de Instagram.
"""

import streamlit as st
import json
import pandas as pd
from pathlib import Path

from pipeline.ingestion import scan_local_folder, process_file, load_registry, load_graph_data
from pipeline.graph_builder import build_graph, compute_metrics, graph_to_sigma_format
from viz.renderer import build_sigma_html

# ── Config ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Social Graph · Curso",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

.stApp {
    background: #0a0a0f;
    color: #e8e8f0;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0e0e1a !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}

/* Títulos */
h1, h2, h3 {
    font-family: 'Space Mono', monospace !important;
    color: #e8e8f0 !important;
}

/* Métricas */
[data-testid="stMetric"] {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 12px 16px !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'Space Mono', monospace !important;
    font-size: 10px !important;
    color: rgba(255,255,255,0.35) !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
[data-testid="stMetricValue"] {
    font-family: 'Space Mono', monospace !important;
    color: #e8e8f0 !important;
}

/* Botones */
.stButton > button {
    background: rgba(124,111,255,0.15) !important;
    border: 1px solid rgba(124,111,255,0.4) !important;
    color: #b8b0ff !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 11px !important;
    border-radius: 6px !important;
    transition: all 0.15s !important;
}
.stButton > button:hover {
    background: rgba(124,111,255,0.25) !important;
    border-color: rgba(124,111,255,0.7) !important;
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.02) !important;
    border: 1px dashed rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
}

/* Expander */
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.02) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 8px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    background: rgba(255,255,255,0.02) !important;
}

/* Info / success / error boxes */
.stAlert {
    border-radius: 8px !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 11px !important;
}

/* Divider */
hr { border-color: rgba(255,255,255,0.07) !important; }

/* Section label */
.section-label {
    font-family: 'Space Mono', monospace;
    font-size: 9px;
    color: rgba(255,255,255,0.3);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 12px;
    margin-top: 20px;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

@st.cache_data(ttl=5)
def get_graph_metrics(only_course: bool):
    G = build_graph(only_course_nodes=only_course)
    metrics = compute_metrics(G)
    sigma_data = graph_to_sigma_format(G, metrics)
    return G, metrics, sigma_data


def status_icon(status: str) -> str:
    return {"added": "✅", "duplicate": "⚠️", "error": "❌", "anonymous": "🔵"}.get(status, "•")


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("# 🕸️ Social Graph")
    st.markdown("<div class='section-label'>Pipeline · Ingesta</div>", unsafe_allow_html=True)

    # ── Scan carpeta local
    with st.expander("📁 Carpetas locales", expanded=False):
        st.caption(
            "`data/raw/following/` — coloca aquí los following.json\n\n"
            "`data/raw/followers/` — coloca aquí los followers.json\n\n"
            "Nombra como `following_username.json` o `followers_username.json` para auto-detectar el owner."
        )
        if st.button("🔄 Escanear carpetas", use_container_width=True):
            with st.spinner("Escaneando..."):
                results = scan_local_folder()
            if not results:
                st.info("No se encontraron archivos JSON en data/raw/following/ ni data/raw/followers/")
            else:
                for r in results:
                    icon = status_icon(r["status"])
                    st.markdown(f"`{icon}` **{r.get('source_name','')}** — {r['message']}")
            get_graph_metrics.clear()

    # ── Upload manual
    st.markdown("<div class='section-label'>Subir archivos</div>", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "following.json / followers.json",
        type=["json"],
        accept_multiple_files=True,
        help="Puedes subir múltiples archivos a la vez",
    )

    if uploaded:
        owner_input = st.text_input(
            "Tu username de Instagram (opcional)",
            placeholder="ej: jorge_mercado12a",
            help="Si subes varios archivos del mismo usuario, escribe el username una sola vez. Puedes dejarlo vacío.",
        )
        owner = owner_input.strip().lower() if owner_input.strip() else None

        if st.button("⬆️ Procesar archivos subidos", use_container_width=True):
            for uf in uploaded:
                content = uf.read()
                result = process_file(content, source_name=uf.name, declared_owner=owner)
                icon = status_icon(result["status"])
                if result["status"] == "error":
                    st.error(f"{icon} **{uf.name}**: {result['message']}")
                elif result["status"] == "duplicate":
                    st.warning(f"{icon} **{uf.name}**: {result['message']}")
                elif result["status"] == "anonymous":
                    st.info(f"{icon} **{uf.name}**: {result['message']}")
                else:
                    st.success(f"{icon} **{uf.name}**: {result['message']}")
            get_graph_metrics.clear()

    st.divider()

    # ── Registro
    st.markdown("<div class='section-label'>Registro</div>", unsafe_allow_html=True)
    registry = load_registry()
    st.metric("Archivos procesados", len(registry))

    if registry:
        with st.expander("Ver registro", expanded=False):
            rows = []
            for fid, meta in registry.items():
                rows.append({
                    "Owner": meta.get("owner") or "—",
                    "Tipo": meta.get("file_type", "—"),
                    "Relaciones": meta.get("relation_count", 0),
                    "Fecha": meta.get("ingested_at", "—")[:10],
                    "Inferido": "Sí" if meta.get("inferred_owner") else "No",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        if st.button("🗑️ Limpiar todo el registro", use_container_width=True):
            Path("data/registry/registry.json").unlink(missing_ok=True)
            Path("data/graph_data.json").unlink(missing_ok=True)
            get_graph_metrics.clear()
            st.rerun()

    st.divider()

    # ── Opciones de grafo
    st.markdown("<div class='section-label'>Opciones del grafo</div>", unsafe_allow_html=True)
    only_course = st.toggle(
        "Solo nodos del curso",
        value=False,
        help="Filtra para mostrar únicamente personas que subieron su archivo",
    )


# ── Main area ────────────────────────────────────────────────────────────────

graph_data_raw = load_graph_data()
node_count = len(graph_data_raw.get("nodes", {}))
anon_files = graph_data_raw.get("anonymous_files", [])

if node_count == 0:
    st.markdown("## Sin datos aún")
    st.markdown("""
    Para comenzar:
    1. Coloca archivos `following.json` en `data/raw/following/` y `followers.json` en `data/raw/followers/`, luego presiona **Escanear carpetas**, o
    2. Sube archivos directamente usando el uploader en la barra lateral.

    Los archivos los exporta Instagram desde: **Configuración → Tu actividad → Descargar tu información**.
    """)
    st.stop()

if anon_files:
    st.warning(
        f"⚠️ **{len(anon_files)} archivo(s) sin owner identificado** — "
        "se muestran sus nodos pero sin arcos de origen. "
        "Se resolverán automáticamente al procesar más archivos, o puedes volver a subirlos declarando el username."
    )

# Cargar grafo y métricas
G, metrics, sigma_data = get_graph_metrics(only_course)
gm = metrics["global"]
per_node = metrics["per_node"]

# ── Métricas globales
st.markdown("## Grafo del curso")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Nodos totales", gm.get("node_count", 0))
col2.metric("Nodos del curso", gm.get("course_node_count", 0))
col3.metric("Conexiones", gm.get("edge_count", 0))
col4.metric("Comunidades", gm.get("community_count", 0))
col5.metric("Densidad", gm.get("density", 0))

st.divider()

# ── Grafo Sigma
st.markdown("<div class='section-label'>Visualización interactiva · Haz clic en un nodo para ver sus métricas</div>", unsafe_allow_html=True)

sigma_html = build_sigma_html(sigma_data, height=680)
st.components.v1.html(sigma_html, height=680, scrolling=False)

st.divider()

# ── Tabla de métricas por nodo
st.markdown("### Ranking de nodos")

tab1, tab2 = st.tabs(["📊 Métricas completas", "🏆 Rankings"])

with tab1:
    rows = []
    for username, m in per_node.items():
        rows.append({
            "Usuario": username,
            "Curso": "✓" if m["has_file"] else "",
            "Seguidores (in)": m["in_degree"],
            "Siguiendo (out)": m["out_degree"],
            "Mutuos": m["mutual_count"],
            "Betweenness": m["betweenness"],
            "PageRank": m["pagerank"],
            "Closeness": m["closeness"],
            "Clustering": m["clustering"],
            "Comunidad": m["community"],
        })

    df = pd.DataFrame(rows).sort_values("PageRank", ascending=False)
    st.dataframe(df, hide_index=True, use_container_width=True, height=400)

with tab2:
    r1, r2, r3 = st.columns(3)

    with r1:
        st.markdown("**🔝 Más seguidos (in-degree)**")
        top_in = sorted(per_node.items(), key=lambda x: x[1]["in_degree"], reverse=True)[:10]
        for i, (u, m) in enumerate(top_in, 1):
            badge = "🎓" if m["has_file"] else "·"
            st.markdown(f"`{i:02d}` {badge} **@{u}** — {m['in_degree']}")

    with r2:
        st.markdown("**🔗 Mayor betweenness**")
        top_btw = sorted(per_node.items(), key=lambda x: x[1]["betweenness"], reverse=True)[:10]
        for i, (u, m) in enumerate(top_btw, 1):
            badge = "🎓" if m["has_file"] else "·"
            st.markdown(f"`{i:02d}` {badge} **@{u}** — {m['betweenness']:.4f}")

    with r3:
        st.markdown("**🤝 Más conexiones mutuas**")
        top_mut = sorted(per_node.items(), key=lambda x: x[1]["mutual_count"], reverse=True)[:10]
        for i, (u, m) in enumerate(top_mut, 1):
            badge = "🎓" if m["has_file"] else "·"
            st.markdown(f"`{i:02d}` {badge} **@{u}** — {m['mutual_count']}")

# ── Archivos anónimos pendientes
if anon_files:
    st.divider()
    with st.expander(f"Ver {len(anon_files)} archivo(s) anónimos pendientes"):
        for af in anon_files:
            st.markdown(f"- `{af['file_type']}` · {len(af['relations'])} relaciones · fuente: `{af['source_name']}`")
