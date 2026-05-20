"""
app.py
------
Aplicación Streamlit para análisis de grafo social de Instagram.
"""

import streamlit as st
import json
import pandas as pd
import tempfile
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
from pipeline.analysis import (
    build_analysis_dataframe,
    get_node_profile,
    get_components_info,
    compute_global_metrics,
)
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


@st.cache_data(ttl=5)
def get_analysis_data():
    G = build_graph(only_course_nodes=False)
    course_nodes = {n for n, d in G.nodes(data=True) if d.get("has_file")}
    df = build_analysis_dataframe(G, course_nodes)
    global_m = compute_global_metrics(G)
    components = get_components_info(G, course_nodes)
    return G, df, global_m, components, course_nodes


def status_icon(status: str) -> str:
    return {"added": "✅", "duplicate": "⚠️", "error": "❌", "anonymous": "🔵"}.get(status, "•")


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("# 🕸️ Social Graph")

    # ── 1. Upload emparejado ─────────────────────────────────────────────────
    with st.expander("⬆️ Subir archivos", expanded=False):
        with st.form("upload_form", clear_on_submit=True):
            username_input = st.text_input(
                "👤 Username de Instagram",
                placeholder="ej: tu_usuario",
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

            submitted = st.form_submit_button("⬆️ Subir", width="stretch")

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
        if st.button("🔄 Escanear carpetas", width="stretch"):
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
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.divider()

    # ── 5. Zona peligrosa ─────────────────────────────────────────────────────
    with st.expander("⚠️ Zona peligrosa", expanded=False):
        st.caption(
            "Esto borra **todos** los datos: registry, grafo, y archivos en raw/ e incompleto/. "
            "No se puede deshacer."
        )
        if st.button("🗑️ Reset completo", width="stretch", type="primary"):
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

# ── Pestañas principales ──────────────────────────────────────────────────────
tab_grafo, tab_analisis = st.tabs(["Grafo", "Análisis"])


# ════════════════════════════════════════════════════════════════════════════
# PESTAÑA 1 — GRAFO
# ════════════════════════════════════════════════════════════════════════════
with tab_grafo:
    G, metrics, sigma_data = get_graph_metrics(False)
    gm = metrics["global"]
    per_node = metrics["per_node"]

    st.markdown("## Grafo del curso")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Nodos totales", gm.get("node_count", 0))
    col2.metric("Nodos del curso", gm.get("course_node_count", 0))
    col3.metric("Conexiones", gm.get("edge_count", 0))
    col4.metric("Comunidades", gm.get("community_count", 0))
    col5.metric("Densidad", gm.get("density", 0))

    st.divider()

    st.markdown(
        "<div class='section-label'>Visualización interactiva · Haz clic en un nodo para ver sus métricas</div>",
        unsafe_allow_html=True,
    )

    sigma_html = build_sigma_html(sigma_data, height=680)
    st.components.v1.html(sigma_html, height=680, scrolling=False)

    st.divider()

    st.markdown("<div class='section-label'>Dataset de nodos</div>", unsafe_allow_html=True)

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

    df_full = pd.DataFrame(rows).sort_values("PageRank", ascending=False)
    st.dataframe(df_full, hide_index=True, width="stretch", height=400)

    if anon_files:
        st.divider()
        with st.expander(f"Ver {len(anon_files)} archivo(s) anónimos pendientes"):
            for af in anon_files:
                label = af.get("assigned_owner", "—")
                st.markdown(
                    f"- `{af['file_type']}` · {len(af['relations'])} relaciones · "
                    f"asignado como `@{label}` · fuente: `{af['source_name']}`"
                )


# ════════════════════════════════════════════════════════════════════════════
# PESTAÑA 2 — ANÁLISIS
# ════════════════════════════════════════════════════════════════════════════
with tab_analisis:
    G_a, df_a, global_m, components, course_nodes = get_analysis_data()

    st.markdown("## Análisis estructural")
    st.markdown(
        "<div class='section-label'>Enfocado en las 11 personas del curso · nodos externos aparecen si son estructuralmente relevantes</div>",
        unsafe_allow_html=True,
    )

    # ── Métricas globales ─────────────────────────────────────────────────────
    st.markdown("### Grafo completo")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nodos", global_m["node_count"])
    c2.metric("Arcos", global_m["edge_count"])
    c3.metric("Densidad", global_m["density"],
              help="Fracción de conexiones posibles que realmente existen. 0 = desconectado, 1 = todos conectados con todos.")
    c4.metric("Reciprocidad", global_m["reciprocity"],
              help="Fracción de arcos que tienen contrapartida (A→B y B→A). Indica cuántas relaciones son mutuas.")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Componentes", global_m["weakly_connected_components"],
              help="Grupos de nodos sin conexión entre sí.")
    c6.metric("Componente principal", global_m["main_component_size"],
              help="Cantidad de nodos en el grupo conectado más grande.")
    c7.metric("Diámetro", global_m["diameter"] if global_m["diameter"] is not None else "—",
              help="Mayor distancia mínima entre dos nodos de la componente principal.")
    c8.metric("Camino promedio", global_m["avg_shortest_path"] if global_m["avg_shortest_path"] is not None else "—",
              help="Promedio de la distancia mínima entre todos los pares de nodos.")

    st.divider()

    # ── Ranking de métricas ───────────────────────────────────────────────────
    st.markdown("### Rankings por métrica")

    col_metric_sel, col_scope_sel = st.columns([2, 1])
    with col_metric_sel:
        metric_choice = st.selectbox(
            "Ordenar por",
            options=["pagerank", "betweenness", "in_degree", "out_degree",
                     "degree_centrality", "closeness", "reciprocity", "clustering", "mutual_count"],
            format_func=lambda x: {
                "pagerank":          "PageRank — influencia ponderada",
                "betweenness":       "Betweenness — nodos puente",
                "in_degree":         "In-degree — más seguidos",
                "out_degree":        "Out-degree — más activos siguiendo",
                "degree_centrality": "Degree centrality — conectividad global",
                "closeness":         "Closeness — cercanía a todos",
                "reciprocity":       "Reciprocidad — relaciones mutuas",
                "clustering":        "Clustering — vecindad cerrada",
                "mutual_count":      "Mutuos — follows recíprocos",
            }[x],
        )
    with col_scope_sel:
        show_scope = st.radio(
            "Mostrar",
            options=["Solo curso", "Top 20 global"],
            horizontal=True,
        )

    if show_scope == "Solo curso":
        df_ranked = df_a[df_a["en_curso"]].sort_values(metric_choice, ascending=False).reset_index(drop=True)
    else:
        df_ranked = df_a.sort_values(metric_choice, ascending=False).head(20).reset_index(drop=True)

    # Añadir columna de rango y etiqueta de curso
    df_display = df_ranked.copy()
    df_display.insert(0, "#", range(1, len(df_display) + 1))
    df_display["en_curso"] = df_display["en_curso"].map({True: "✓", False: ""})
    df_display = df_display.rename(columns={
        "usuario": "Usuario",
        "en_curso": "Curso",
        "in_degree": "In",
        "out_degree": "Out",
        "degree_centrality": "Degree C.",
        "betweenness": "Betweenness",
        "pagerank": "PageRank",
        "closeness": "Closeness",
        "clustering": "Clustering",
        "reciprocity": "Reciprocidad",
        "mutual_count": "Mutuos",
    })

    st.dataframe(
        df_display,
        hide_index=True,
        width="stretch",
        height=380,
        column_config={
            "PageRank":    st.column_config.ProgressColumn("PageRank", min_value=0, max_value=float(df_a["pagerank"].max() or 1), format="%.5f"),
            "Betweenness": st.column_config.ProgressColumn("Betweenness", min_value=0, max_value=float(df_a["betweenness"].max() or 1), format="%.4f"),
        },
    )

    st.divider()

    # ── Comparativa visual del curso ─────────────────────────────────────────
    st.markdown("### Comparativa de personas del curso")

    df_course = df_a[df_a["en_curso"]].sort_values("pagerank", ascending=False).copy()

    chart_metric = st.selectbox(
        "Métrica a visualizar",
        options=["pagerank", "betweenness", "in_degree", "out_degree",
                 "degree_centrality", "closeness", "reciprocity", "mutual_count"],
        format_func=lambda x: {
            "pagerank":          "PageRank",
            "betweenness":       "Betweenness",
            "in_degree":         "In-degree (seguidores)",
            "out_degree":        "Out-degree (siguiendo)",
            "degree_centrality": "Degree Centrality",
            "closeness":         "Closeness",
            "reciprocity":       "Reciprocidad",
            "mutual_count":      "Conexiones mutuas",
        }[x],
        key="chart_metric",
    )

    chart_df = df_course[["usuario", chart_metric]].sort_values(chart_metric, ascending=False)
    chart_df = chart_df.rename(columns={"usuario": "index"}).set_index("index")
    st.bar_chart(chart_df, height=280)

    st.divider()

    # ── Componentes conectadas ───────────────────────────────────────────────
    st.markdown("### Componentes conectadas")

    for comp in components:
        size = comp["size"]
        c_count = comp["course_count"]
        label = f"Componente {comp['id'] + 1} — {size} nodos"
        if c_count:
            label += f" ({c_count} del curso)"

        with st.expander(label, expanded=(comp["id"] == 0)):
            if comp["course_nodes"]:
                st.markdown(
                    "**Personas del curso:** " +
                    " · ".join(f"`@{n}`" for n in sorted(comp["course_nodes"]))
                )
            else:
                st.caption("Ninguna persona del curso en esta componente.")
            st.caption(f"Total nodos: {size}")

    st.divider()

    # ── Perfil individual ─────────────────────────────────────────────────────
    st.markdown("### Perfil individual")

    course_list = sorted(course_nodes)
    selected_user = st.selectbox(
        "Selecciona una persona del curso",
        options=course_list,
        format_func=lambda x: f"@{x}",
    )

    if selected_user:
        profile = get_node_profile(G_a, selected_user, df_a)
        m = profile.get("metrics", {})

        st.markdown(f"#### @{selected_user}")

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Seguidores (in)", m.get("in_degree", "—"))
        p2.metric("Siguiendo (out)", m.get("out_degree", "—"))
        p3.metric("Mutuos", m.get("mutual_count", "—"))
        p4.metric("Reciprocidad", m.get("reciprocity", "—"))

        p5, p6, p7, p8 = st.columns(4)
        p5.metric("PageRank", m.get("pagerank", "—"),
                  help="Importancia según la calidad de quién te sigue.")
        p6.metric("Betweenness", m.get("betweenness", "—"),
                  help="Fracción de caminos más cortos que pasan por este nodo.")
        p7.metric("Closeness", m.get("closeness", "—"),
                  help="Qué tan cerca está de todos los demás en promedio.")
        p8.metric("Clustering", m.get("clustering", "—"),
                  help="Qué tan interconectados están sus vecinos.")

        # Rangos dentro del curso
        df_course_ranked = df_a[df_a["en_curso"]].copy()
        total_course = len(df_course_ranked)

        def rank_in_course(col):
            ranked = df_course_ranked.sort_values(col, ascending=False).reset_index(drop=True)
            idx = ranked[ranked["usuario"] == selected_user].index
            return int(idx[0]) + 1 if len(idx) else "—"

        st.markdown("**Posición dentro del curso:**")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("PageRank", f"#{rank_in_course('pagerank')} / {total_course}")
        r2.metric("Betweenness", f"#{rank_in_course('betweenness')} / {total_course}")
        r3.metric("In-degree", f"#{rank_in_course('in_degree')} / {total_course}")
        r4.metric("Out-degree", f"#{rank_in_course('out_degree')} / {total_course}")

        st.divider()

        # Conexiones
        col_left, col_right = st.columns(2)

        with col_left:
            follows = profile.get("follows", [])
            st.markdown(f"**Sigue a** ({len(follows)} usuarios)")
            course_follows = [f for f in follows if f in course_nodes]
            ext_follows = [f for f in follows if f not in course_nodes]
            if course_follows:
                st.caption("Del curso:")
                st.markdown(" · ".join(f"`@{u}`" for u in sorted(course_follows)))
            if ext_follows:
                with st.expander(f"Externos ({len(ext_follows)})", expanded=False):
                    st.markdown(
                        "\n".join(f"- @{u}" for u in sorted(ext_follows)[:50])
                    )

        with col_right:
            followers = profile.get("followers", [])
            st.markdown(f"**Seguido por** ({len(followers)} usuarios)")
            course_followers = [f for f in followers if f in course_nodes]
            ext_followers = [f for f in followers if f not in course_nodes]
            if course_followers:
                st.caption("Del curso:")
                st.markdown(" · ".join(f"`@{u}`" for u in sorted(course_followers)))
            if ext_followers:
                with st.expander(f"Externos ({len(ext_followers)})", expanded=False):
                    st.markdown(
                        "\n".join(f"- @{u}" for u in sorted(ext_followers)[:50])
                    )

        # Nodos puente relacionados
        bridge_nodes = profile.get("bridge_nodes", [])
        if bridge_nodes:
            st.divider()
            st.markdown("**Nodos puente en su vecindad** (vecinos con mayor betweenness)")
            bcols = st.columns(min(len(bridge_nodes), 5))
            for i, (bnode, bval) in enumerate(bridge_nodes):
                with bcols[i]:
                    badge = "Curso" if bnode in course_nodes else "Externo"
                    st.metric(f"@{bnode}", f"{bval:.4f}", delta=badge, delta_color="off")
