"""
Proyecto v4 - Agente Inteligente de Análisis Financiero.
Combina: datos locales en DuckDB (como la v2, archivos .txt/.xlsx) +
toda la lógica de clasificación validada en la v3 (mapeo real por
empresa) + la interfaz mejorada (sin dashboard automático, selector de
partidas en cajitas, botón de IA fijo arriba a la derecha, subtotales).

Cómo correrla:
    py -m pip install -r requirements.txt
    python 06_cargar_todo.py          (primera vez, o cuando lleguen datos nuevos)
    $env:ANTHROPIC_API_KEY="tu-key"
    python -m streamlit run app.py
"""
import os
from importlib import import_module, reload

import duckdb
import pandas as pd
import streamlit as st

agente = import_module("09_agente_loop")
dash = import_module("10_dashboard")
detalle = import_module("14_dashboard_detalle")
conv = import_module("11_conversaciones")

agente = reload(agente)
dash = reload(dash)
detalle = reload(detalle)
conv = reload(conv)

DB_PATH = "data/financiero_v2.duckdb"


def asegurar_base_de_datos():
    """Descarga data/financiero_v2.duckdb desde un GitHub Release privado
    si no existe localmente (el archivo pesa ~300MB, no cabe en un repo
    de Git normal). Mismo mecanismo que ya usamos en la v2."""
    if os.path.exists(DB_PATH):
        return

    def _config(nombre):
        valor = os.environ.get(nombre)
        if valor:
            return valor
        try:
            return st.secrets.get(nombre)
        except Exception:
            return None

    token, repo = _config("GITHUB_TOKEN"), _config("GITHUB_REPO")
    tag = _config("GITHUB_RELEASE_TAG") or "v4-data"
    if not (token and repo):
        return

    import urllib.request, json
    with st.spinner("Descargando la base de datos (solo la primera vez)..."):
        h_api = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", headers=h_api)
        with urllib.request.urlopen(req) as resp:
            release = json.loads(resp.read())
        asset = next(a for a in release["assets"] if a["name"] == "financiero_v2.duckdb")
        h_dl = {"Authorization": f"token {token}", "Accept": "application/octet-stream"}
        req2 = urllib.request.Request(asset["url"], headers=h_dl)
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with urllib.request.urlopen(req2) as resp2, open(DB_PATH, "wb") as f:
            f.write(resp2.read())


asegurar_base_de_datos()


st.set_page_config(page_title="Agente Inteligente de Análisis Financiero", page_icon="📊", layout="wide")

EMPRESAS_POR_PAIS = dash.EMPRESAS_POR_PAIS
TODAS_LAS_EMPRESAS = [e for lista in EMPRESAS_POR_PAIS.values() for e in lista]
EMPRESA_A_PAIS = {e: p for p, lista in EMPRESAS_POR_PAIS.items() for e in lista}


# ─────────────────────────────────────────────────────────────────────────
# Paso 1: nombre de usuario
# ─────────────────────────────────────────────────────────────────────────
if "usuario" not in st.session_state:
    st.title("📊 Agente Inteligente de Análisis Financiero (v4)")
    st.subheader("¿Cómo te llamas?")
    nombre = st.text_input("Nombre", placeholder="Ej: Paola Rodríguez")
    if st.button("Entrar", type="primary") and nombre.strip():
        st.session_state.usuario = nombre.strip()
        st.rerun()
    st.stop()

usuario = st.session_state.usuario

if "modo" not in st.session_state:
    st.session_state.modo = "sin_filtro"
if "mensajes" not in st.session_state:
    st.session_state.mensajes = []
if "filtros_al_guardar" not in st.session_state:
    st.session_state.filtros_al_guardar = {}


# ─────────────────────────────────────────────────────────────────────────
# Paso 2: conectar a la base local
# ─────────────────────────────────────────────────────────────────────────
if "con_db" not in st.session_state:
    if not os.path.exists(DB_PATH):
        st.error(f"⚠️ No encuentro {DB_PATH}. Corre primero: python 06_cargar_todo.py")
        st.stop()
    st.session_state.con_db = duckdb.connect(DB_PATH, read_only=True)

con_db = st.session_state.con_db


# ─────────────────────────────────────────────────────────────────────────
# Barra lateral
# ─────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📊 Agente Inteligente de Análisis Financiero")
    st.caption(f"Conectado como **{usuario}**")
    st.divider()

    estado_financiero = st.selectbox(
        "Estado Financiero", ["Estado de Resultados (GYP)"],
        help="Por ahora solo Estado de Resultados está disponible en esta versión.",
    )

    pais = st.selectbox("País", ["Colombia", "Costa Rica", "Venezuela", "Global (todas)"])
    opciones_empresa = TODAS_LAS_EMPRESAS if pais == "Global (todas)" else EMPRESAS_POR_PAIS[pais]
    empresas = st.multiselect("Empresa(s)", opciones_empresa, default=opciones_empresa)

    paises_involucrados = {EMPRESA_A_PAIS[e] for e in empresas}
    if len(paises_involucrados) > 1:
        moneda_label = "Dólares (USD)"
        st.caption("⚠️ Moneda forzada a USD: seleccionaste empresas de más de un país.")
    else:
        moneda_label = st.radio("Moneda", ["Dólares (USD)", "Moneda local"], horizontal=True)
    moneda = "USD" if moneda_label == "Dólares (USD)" else "LOCAL"

    st.divider()
    if st.button("🔍 Ver categorías", type="primary", use_container_width=True):
        st.session_state.modo = "seleccionar_partida"
        st.rerun()
    if st.button("🆕 Nueva conversación"):
        st.session_state.mensajes = []
        st.session_state.modo = "chat"
        st.rerun()

    st.divider()
    st.subheader("Tus conversaciones guardadas")
    guardadas = conv.listar_conversaciones(usuario)
    if not guardadas:
        st.caption("Todavía no tienes ninguna guardada.")
    for g in guardadas[:15]:
        etiqueta = f"{g['titulo']} — {g['fecha'].strftime('%d/%m %H:%M')}"
        col_cargar, col_borrar = st.columns([5, 1])
        with col_cargar:
            if st.button(etiqueta, key=f"cargar_{g['id']}", use_container_width=True):
                cargada = conv.cargar_conversacion(g["id"])
                st.session_state.mensajes = cargada["mensajes"]
                st.session_state.modo = "chat"
                st.rerun()
        with col_borrar:
            if st.button("🗑️", key=f"borrar_{g['id']}", help="Borrar esta conversación"):
                conv.eliminar_conversacion(g["id"])
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────
# Validar API key de Claude
# ─────────────────────────────────────────────────────────────────────────
def _config(nombre):
    valor = os.environ.get(nombre)
    if valor:
        return valor
    try:
        return st.secrets.get(nombre)
    except Exception:
        return None

api_key = _config("ANTHROPIC_API_KEY")
workspace_id = _config("ANTHROPIC_WORKSPACE_ID")
if not api_key:
    st.error("⚠️ Falta configurar ANTHROPIC_API_KEY antes de poder usar el agente.")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────
# Helpers de presentación
# ─────────────────────────────────────────────────────────────────────────
def _contexto_filtros_texto() -> str:
    emp_txt = ", ".join(empresas) if empresas else "(ninguna seleccionada)"
    return f"Estado Financiero: Estado de Resultados (GYP) | País: {pais} | Empresa(s): {emp_txt} | Moneda: {moneda_label}"


def _encabezado_con_boton_ia(titulo: str):
    col_titulo, col_boton = st.columns([4, 1])
    with col_titulo:
        st.title(titulo)
    with col_boton:
        st.write("")
        if st.button("🔎 Analizar con IA", type="primary", use_container_width=True):
            st.session_state.modo = "chat"
            st.session_state.filtros_al_guardar = {
                "estado_financiero": "Estado de Resultados (GYP)", "pais": pais,
                "empresas": empresas, "moneda": moneda_label,
            }
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────
# SIN FILTRO
# ─────────────────────────────────────────────────────────────────────────
if st.session_state.modo == "sin_filtro":
    st.title("📊 Agente Inteligente de Análisis Financiero")
    st.info("👈 Elige un País y una o más Empresas en la barra lateral, y luego dale clic a **'🔍 Ver categorías'** para comenzar.")


# ─────────────────────────────────────────────────────────────────────────
# SELECCIONAR PARTIDA (cajitas, sin consulta previa)
# ─────────────────────────────────────────────────────────────────────────
elif st.session_state.modo == "seleccionar_partida":
    _encabezado_con_boton_ia("📊 Agente Inteligente de Análisis Financiero")
    st.caption(_contexto_filtros_texto())

    if not empresas:
        st.warning("Selecciona al menos una empresa en la barra lateral.")
        st.stop()

    st.subheader("Elige una partida para ver su detalle")
    columnas_por_fila = 4
    for inicio in range(0, len(dash.CATEGORIAS_DASHBOARD), columnas_por_fila):
        cols = st.columns(columnas_por_fila)
        for col, categoria in zip(cols, dash.CATEGORIAS_DASHBOARD[inicio:inicio + columnas_por_fila]):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{categoria}**")
                    if st.button("Ver detalle", key=f"partida_{categoria}", use_container_width=True):
                        st.session_state.modo = "detalle_categoria"
                        st.session_state.categoria_detalle = categoria
                        st.rerun()


# ─────────────────────────────────────────────────────────────────────────
# DETALLE POR PARTIDA
# ─────────────────────────────────────────────────────────────────────────
elif st.session_state.modo == "detalle_categoria":
    categoria = st.session_state.categoria_detalle
    if st.button("← Volver a categorías"):
        st.session_state.modo = "seleccionar_partida"
        st.rerun()

    _encabezado_con_boton_ia(f"📌 {categoria}")
    st.caption(_contexto_filtros_texto())

    tab1, tab2, tab3, tab4 = st.tabs([
        "Tendencia y Centro de Costo", "Variación Mensual",
        "Gasto vs. Ventas", "Real vs. Presupuesto",
    ])

    with tab1:
        with st.spinner("Consultando..."):
            df_cc = detalle.tendencia_y_centro_costo(con_db, empresas, categoria, moneda)
        if df_cc.empty:
            st.info("No hay movimientos para esta partida con los filtros actuales.")
        else:
            total_mensual = df_cc.groupby("mes", as_index=False)["monto"].sum()
            st.line_chart(total_mensual.set_index("mes")[["monto"]])
            st.caption("Tendencia total de la partida (todos los centros de costo sumados).")
            col_a, col_b = st.columns(2)
            with col_a:
                valores_cc = df_cc["CENTRO_COSTO"].dropna().astype(str).unique().tolist()
                cc_elegido = st.selectbox("Centro de Costo", ["(todos)"] + sorted(valores_cc))
            with col_b:
                meses_disponibles = sorted(df_cc["mes"].dt.strftime("%Y-%m-%d").unique().tolist(), reverse=True)
                mes_elegido = st.selectbox("Mes", ["(todos)"] + meses_disponibles)

            if cc_elegido != "(todos)":
                serie_cc = df_cc[df_cc["CENTRO_COSTO"] == cc_elegido].set_index("mes")[["monto"]]
                st.bar_chart(serie_cc)

            with st.spinner("Buscando movimientos..."):
                top = detalle.top_movimientos(
                    con_db, empresas, categoria, moneda,
                    centro_costo=None if cc_elegido == "(todos)" else cc_elegido,
                    mes=None if mes_elegido == "(todos)" else mes_elegido,
                )
            st.dataframe(top, hide_index=True, use_container_width=True)

    with tab2:
        serie = df_cc.groupby("mes", as_index=False)["monto"].sum() if not df_cc.empty else pd.DataFrame(columns=["mes", "monto"])
        df_var = detalle.variacion_mensual(serie)
        if df_var.empty:
            st.info("Sin datos suficientes para calcular la variación.")
        else:
            st.bar_chart(df_var.set_index("mes")[["variacion_pct"]])
            st.caption("Variación % de cada mes contra el mes INMEDIATAMENTE ANTERIOR.")
            st.dataframe(df_var, hide_index=True, use_container_width=True)

    with tab3:
        with st.spinner("Consultando..."):
            df_ventas = detalle.gasto_sobre_ventas(con_db, empresas, categoria, moneda)
        if df_ventas.empty:
            st.info("Sin datos suficientes.")
        else:
            st.line_chart(df_ventas.set_index("mes")[["pct_sobre_ventas"]])
            st.dataframe(df_ventas, hide_index=True, use_container_width=True)

    with tab4:
        with st.spinner("Consultando..."):
            df_rvp = detalle.real_vs_presupuesto(con_db, empresas, categoria, moneda)
        if df_rvp.empty or df_rvp["presupuesto_monto"].isna().all():
            st.info("Esta categoría no tiene presupuesto asignado (o el presupuesto no cubre el período de estos datos).")
        if not df_rvp.empty:
            st.bar_chart(df_rvp.set_index("mes")[["real_monto", "presupuesto_monto"]])
            st.dataframe(df_rvp, hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────────────────────────────────
else:
    st.title("Analista Financiero IA")
    st.caption(_contexto_filtros_texto() + " — este contexto se envía junto con cada pregunta.")

    for m in st.session_state.mensajes:
        with st.chat_message(m["role"]):
            if m["role"] == "assistant" and m.get("sql_ejecutados"):
                st.markdown(m["contenido"])
                exitosos = [i for i in m["sql_ejecutados"] if i["resultado"]["ok"]]
                if exitosos and exitosos[-1]["resultado"]["filas"]:
                    st.dataframe(pd.DataFrame(exitosos[-1]["resultado"]["filas"]), width="stretch")
                with st.expander(f"🔍 Ver SQL ejecutado ({len(m['sql_ejecutados'])} consulta(s))"):
                    for item in m["sql_ejecutados"]:
                        st.code(item["query"], language="sql")
            else:
                st.markdown(m["contenido"])

    pregunta = st.chat_input("Ej: ¿por qué subió el gasto de personal en julio?")
    if pregunta:
        historial_previo = [
            {"role": m["role"], "content": m["contenido"]}
            for m in st.session_state.mensajes[-6:]
        ]

        st.session_state.mensajes.append({"role": "user", "contenido": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)

        pregunta_con_contexto = f"[Contexto activo: {_contexto_filtros_texto()}]\n\nPregunta: {pregunta}"

        with st.chat_message("assistant"):
            with st.spinner("Consultando la base de datos financiera..."):
                try:
                    resultado = agente.preguntar_al_agente(
                        pregunta_con_contexto, api_key, workspace_id, historial_previo
                    )
                except Exception as e:
                    resultado = {"respuesta": f"⚠️ Ocurrió un error inesperado: {e}", "sql_ejecutados": []}
            st.markdown(resultado["respuesta"])
            exitosos = [i for i in resultado["sql_ejecutados"] if i["resultado"]["ok"]]
            if exitosos and exitosos[-1]["resultado"]["filas"]:
                st.dataframe(pd.DataFrame(exitosos[-1]["resultado"]["filas"]), width="stretch")
            if resultado["sql_ejecutados"]:
                with st.expander(f"🔍 Ver SQL ejecutado ({len(resultado['sql_ejecutados'])} consulta(s))"):
                    for item in resultado["sql_ejecutados"]:
                        st.code(item["query"], language="sql")

        st.session_state.mensajes.append({
            "role": "assistant", "contenido": resultado["respuesta"],
            "sql_ejecutados": resultado["sql_ejecutados"],
        })

    st.divider()
    col1, col2 = st.columns([3, 1])
    with col1:
        titulo_guardar = st.text_input("Título para guardar esta conversación", placeholder="Ej: Gasto de personal Q3")
    with col2:
        st.write("")
        st.write("")
        if st.button("💾 Guardar conversación", use_container_width=True):
            if not st.session_state.mensajes:
                st.warning("No hay nada que guardar todavía.")
            else:
                titulo = titulo_guardar.strip() or f"Conversación {len(st.session_state.mensajes)} mensajes"
                conv.guardar_conversacion(usuario, titulo, st.session_state.filtros_al_guardar, st.session_state.mensajes)
                st.success("Conversación guardada.")
