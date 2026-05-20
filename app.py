"""
app.py
------
Aplicación Streamlit para análisis de grafo social de Instagram.
"""

import streamlit as st
import json
import pandas as pd
from pathlib import Path

from pipeline.ingestion import (
    scan_local_folder,
    process_paired_upload,
    load_registry,
    load_graph_data,
    reset_all_data,
    get_completeness,
    check_and_migrate_version,
    VERSION_PATH,
    DATA_VERSION,
    RAW_FOLLOWING_PATH,
    RAW_FOLLOWERS_PATH,
    INC_FOLLOWING_PATH,
    INC_FOLLOWERS_PATH,
)
from pipeline.graph_builder import build_graph, compute_metrics, graph_to_sigma_format
from viz.renderer import build_sigma_html

# ── Migración de versión (una sola vez por arranque) ─────────────────────────
check_and_migrate_version()

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

[data-testid="stSidebar"] {
    background: #0e0e1a !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}

h1, h2, h3 {
    font-family: 'Space Mono', monospace !important;
    color: #e8e8f0 !important;
}

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

[data-testid="stFileUploader"] {
    background: rgba(255,255,255,0.02) !important;
    border: 1px dashed rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
}

[data-testid="stExpander"] {
    background: rgba(255,255,255,0.02) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 8px !important;
}

[data-testid="stDataFrame"] {
    background: rgba(255,255,255,0.02) !important;
}

.stAlert {
    border-radius: 8px !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 11px !important;
}

hr { border-color: rgba(255,255,255,0.07) !important; }

.section-label {
    font-family: 'Space Mono', monospace;
    font-size: 9px;
    color: rgba(255,255,255,0.3);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 12px;
    margin-top: 20px;
}

/* Danger zone expander: red tint */
.danger-expander [data-testid="stExpander"] {
    border-color: rgba(230,57,70,0.3) !important;
    background: rgba(230,57,70,0.04) !important;
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

    # ── 1. Upload emparejado ─────────────────────────────────────────────────
    st.markdown("<div class='section-label'>Subir archivos</div>", unsafe_allow_html=True)

    with st.form("upload_form", clear_on_submit=True):
        username_input = st.text_input(
            "👤 Username de Instagram",
            placeholder="ej: jorge_mercado12a",
            help="Requerido. Debe coincidir con tu usuario real de Instagram.",
        )

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            following_file = st.file_uploader(
                "📤 following.json",
                type=["json"],
                key="following_upload",
                help="Exportado desde Instagram → Configuración → Tu actividad → Descargar tu información",
            )
        with col_f2:
            followers_file = st.file_uploader(
                "📤 followers*.json",
                type=["json"],
                key="followers_upload",
                help="Puede llamarse followers_1.json u otro nombre que comience con 'followers'",
            )

        submitted = st.form_submit_button("⬆️ Subir", use_container_width=True)

    if submitted:
        username_clean = username_input.strip().lower() if username_input else ""
        has_following = following_file is not None
        has_followers = followers_file is not None

        if not username_clean:
            st.sidebar.error("⚠️ Debes ingresar tu username de Instagram.")
        elif not has_following and not has_followers:
            st.sidebar.error("⚠️ Sube al menos un archivo (following.json o followers.json).")
        else:
            following_bytes = following_file.read() if has_following else None
            followers_bytes = followers_file.read() if has_followers else None

            with st.sidebar:
                with st.spinner("Procesando..."):
                    outcome = process_paired_upload(
                        username=username_clean,
                        following_content=following_bytes,
                        following_name=following_file.name if has_following else "",
                        followers_content=followers_bytes,
                        followers_name=followers_file.name if has_followers else "",
                    )

            for r in outcome["results"]:
                icon = status_icon(r["status"])
                fn = r.get("source_name", "archivo")
                if r["status"] == "error":
                    st.sidebar.error(f"{icon} **{fn}**: {r['message']}")
                elif r["status"] == "duplicate":
                    st.sidebar.warning(f"{icon} **{fn}**: {r['message']}")
                else:
                    st.sidebar.success(f"{icon} **{fn}**: {r['message']}")

            if outcome["is_complete"]:
                st.sidebar.success(f"✅ **@{outcome['owner']}** — perfil completo (following + followers).")
            else:
                st.sidebar.info(
                    f"🔵 **@{outcome['owner']}** — perfil incompleto. "
                    "Sube el archivo que falta para completarlo."
                )

            get_graph_metrics.clear()

    st.divider()

    # ── 2. Scan carpeta local ────────────────────────────────────────────────
    st.markdown("<div class='section-label'>Carpetas locales</div>", unsafe_allow_html=True)

    with st.expander("📁 Escanear carpetas", expanded=False):
        st.caption(
            "`data/raw/following/` — following.json\n\n"
            "`data/raw/followers/` — followers.json\n\n"
            "`data/incompleto/following/` y `data/incompleto/followers/` — archivos incompletos\n\n"
            "Nombra como `following_username.json` para auto-detectar el owner."
        )
        if st.button("🔄 Escanear carpetas", use_container_width=True):
            with st.spinner("Escaneando..."):
                results = scan_local_folder()
            if not results:
                st.info("No se encontraron archivos JSON en las carpetas.")
            else:
                for r in results:
                    icon = status_icon(r["status"])
                    st.markdown(f"`{icon}` **{r.get('source_name','')}** — {r['message']}")
            get_graph_metrics.clear()

    st.divider()

    # ── 3. Estado de completitud ─────────────────────────────────────────────
    st.markdown("<div class='section-label'>Completitud</div>", unsafe_allow_html=True)

    registry = load_registry()
    completeness = get_completeness(registry)
    n_complete = len(completeness["complete"])
    n_incomplete = len(completeness["incomplete"])

    c1, c2 = st.columns(2)
    c1.metric("Completos ✅", n_complete)
    c2.metric("Incompletos 🔵", n_incomplete)

    if n_incomplete:
        with st.expander(f"Ver {n_incomplete} usuario(s) incompletos", expanded=False):
            for owner, info in completeness["incomplete"].items():
                missing_label = "followers" if info["missing"] == "followers" else "following"
                st.markdown(f"- **@{owner}** — tiene `{info['has']}`, falta `{missing_label}`")

    st.divider()

    # ── 4. Registro ──────────────────────────────────────────────────────────
    st.markdown("<div class='section-label'>Registro</div>", unsafe_allow_html=True)

    # Count only real file entries (skip meta keys like _anon_counter)
    real_entries = {k: v for k, v in registry.items() if not k.startswith("_")}
    st.metric("Archivos procesados", len(real_entries))

    if real_entries:
        with st.expander("Ver registro", expanded=False):
            rows = []
            for fid, meta in real_entries.items():
                rows.append({
                    "Owner": meta.get("owner") or "—",
                    "Tipo": meta.get("file_type", "—"),
                    "Completo": "✅" if meta.get("is_complete") else "🔵",
                    "Relaciones": meta.get("relation_count", 0),
                    "Fecha": meta.get("ingested_at", "—")[:10],
                    "Inferido": "Sí" if meta.get("inferred_owner") else "No",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.divider()

    # ── 5. Opciones del grafo ─────────────────────────────────────────────────
    st.markdown("<div class='section-label'>Opciones del grafo</div>", unsafe_allow_html=True)
    only_course = st.toggle(
        "Solo nodos del curso",
        value=False,
        help="Filtra para mostrar únicamente personas que subieron su archivo",
    )

    st.divider()

    # ── 6. Zona peligrosa ─────────────────────────────────────────────────────
    with st.expander("⚠️ Zona peligrosa", expanded=False):
        st.caption(
            "Esto borra **todos** los datos: registry, grafo, y archivos en raw/ e incompleto/. "
            "No se puede deshacer."
        )
        if st.button("🗑️ Reset completo", use_container_width=True, type="primary"):
            reset_all_data()
            # Write version file so we don't auto-reset on next load
            VERSION_PATH.parent.mkdir(parents=True, exist_ok=True)
            VERSION_PATH.write_text(DATA_VERSION)
            st.session_state.clear()
            get_graph_metrics.clear()
            st.rerun()


# ── Main area ────────────────────────────────────────────────────────────────

graph_data_raw = load_graph_data()
node_count = len(graph_data_raw.get("nodes", {}))
anon_files = graph_data_raw.get("anonymous_files", [])

if node_count == 0:
    st.markdown("## Sin datos aún")
    st.markdown("""
    Para comenzar sube tus archivos de Instagram en la barra lateral:

    1. Escribe tu **username de Instagram**
    2. Sube tu `following.json` y/o `followers*.json`
    3. Presiona **Subir**

    Los archivos los exporta Instagram desde:
    **Configuración → Tu actividad → Descargar tu información → Conexiones**
    """)
    st.stop()

if anon_files:
    st.warning(
        f"⚠️ **{len(anon_files)} archivo(s) sin owner identificado** — "
        "sus nodos aparecen en el grafo como `uniN`. "
        "Se resolverán automáticamente al procesar más archivos, o súbelos de nuevo declarando el username."
    )

# Cargar grafo y métricas
G, metrics, sigma_data = get_graph_metrics(only_course)
gm = metrics["global"]
per_node = metrics["per_node"]

# ── Métricas globales ─────────────────────────────────────────────────────────
st.markdown("## Grafo del curso")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Nodos totales", gm.get("node_count", 0))
col2.metric("Nodos del curso", gm.get("course_node_count", 0))
col3.metric("Conexiones", gm.get("edge_count", 0))
col4.metric("Comunidades", gm.get("community_count", 0))
col5.metric("Densidad", gm.get("density", 0))

st.divider()

# ── Grafo Sigma ───────────────────────────────────────────────────────────────
st.markdown(
    "<div class='section-label'>Visualización interactiva · Haz clic en un nodo para ver sus métricas</div>",
    unsafe_allow_html=True,
)

sigma_html = build_sigma_html(sigma_data, height=680)
st.components.v1.html(sigma_html, height=680, scrolling=False)

st.divider()

# ── Tabla de métricas por nodo ────────────────────────────────────────────────
st.markdown("### Ranking de nodos")

tab1, tab2 = st.tabs(["📊 Métricas completas", "🏆 Rankings"])

with tab1:
    rows = []
    for username, m in per_node.items():
        rows.append({
            "Usuario": username,
            "Curso": "✓" if m["has_file"] else "",
            "Anon": "uni" if m.get("is_anonymous") else "",
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

# ── Archivos anónimos pendientes ──────────────────────────────────────────────
if anon_files:
    st.divider()
    with st.expander(f"Ver {len(anon_files)} archivo(s) anónimos pendientes"):
        for af in anon_files:
            label = af.get("assigned_owner", "—")
            st.markdown(
                f"- `{af['file_type']}` · {len(af['relations'])} relaciones · "
                f"asignado como `@{label}` · fuente: `{af['source_name']}`"
            )
