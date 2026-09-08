"""
Proyecto v4 - Las 4 vistas del dashboard detallado por partida, en DuckDB.
Mismo diseño que la v3, con manejo de los 3 subtotales calculados.
"""
import pandas as pd
from importlib import import_module

cte = import_module("09_cte_clasificacion")
CATEGORIAS_INGRESO = ["01.Margen", "02.Ingresos Mercantiles", "03.Fletes Recuperados", "Rebate", "A.Ventas"]

CATEGORIAS_RENTA_BRUTA = ['01.Margen', '02.Ingresos Mercantiles', '03.Fletes Recuperados', '04.Merma']
CATEGORIAS_GASTOS_OPERATIVOS = [
    '05.Personal', '06.Gastos Varios', '08.Alquileres', '09.Cargo Fijo',
    '18.Logistica', '10.Fletes', '11.Tributos', '12.IVA Atrapado', '13.Incobrables',
]
CATEGORIAS_SEMI_NETO_RESTA = [
    '14.Otros Egresos', '14.1.Perdida Cambiaria', '14.2.Gastos Extraordinarios',
    '14.3.Reservas Eventuales', '15.Intereses', '15.1.Bancos', '15.2.Otros Prestamos',
    '16.Depreciación', '16.Depreciaicion',
]
SUBTOTALES = {
    "Gastos Operativos": {c: 1 for c in CATEGORIAS_GASTOS_OPERATIVOS},
    "Ganancia Operativa": {
        **{c: 1 for c in CATEGORIAS_RENTA_BRUTA},
        **{c: -1 for c in CATEGORIAS_GASTOS_OPERATIVOS},
    },
    "Semi Neto": {
        **{c: 1 for c in CATEGORIAS_RENTA_BRUTA},
        **{c: -1 for c in CATEGORIAS_GASTOS_OPERATIVOS},
        **{c: -1 for c in CATEGORIAS_SEMI_NETO_RESTA},
    },
}


def _es_subtotal(categoria: str) -> bool:
    return categoria in SUBTOTALES


def _col_monto(moneda: str) -> str:
    return "MONTO_DOLAR_NETO" if moneda == "USD" else "MONTO_LOCAL_NETO"


def _rango_ultimos_12_meses(con, empresas: list) -> tuple:
    """
    Último mes con datos reales, PERO exigiendo que ese mes tenga al
    menos 60% del volumen de movimientos de la mediana de los últimos 36
    meses — así se descartan meses claramente incompletos (encontramos
    meses con solo 14-55% del volumen normal, que antes se mostraban
    igual). También se acota a "hoy" para evitar fechas fantasma (algunas
    empresas tienen movimientos automáticos fechados hasta un año a futuro).
    """
    hoy = pd.Timestamp.now().normalize()
    ph = ",".join(f"'{e}'" for e in empresas)
    sql = f"""
        SELECT DATE_TRUNC('month', FECHA) AS mes, COUNT(*) AS n
        FROM mayor_contable
        WHERE Empresa IN ({ph}) AND FECHA <= '{hoy.strftime('%Y-%m-%d')}'
        GROUP BY 1
    """
    conteos = con.execute(sql).fetchdf()
    if conteos.empty:
        return None, None
    conteos = conteos.set_index("mes")["n"]

    fecha_max_absoluta = conteos.index.max()
    ventana_reciente = conteos[conteos.index >= fecha_max_absoluta - pd.DateOffset(months=36)]
    umbral = ventana_reciente.median() * 0.60
    mes_referencia = ventana_reciente[ventana_reciente >= umbral].index.max()

    inicio = mes_referencia - pd.DateOffset(months=11)
    return inicio.strftime("%Y-%m-%d"), mes_referencia.strftime("%Y-%m-%d")


def tendencia_y_centro_costo(con, empresas: list, categoria: str, moneda: str) -> pd.DataFrame:
    col = _col_monto(moneda)
    ph = ",".join(f"'{e}'" for e in empresas)
    inicio, fin = _rango_ultimos_12_meses(con, empresas)
    if inicio is None:
        return pd.DataFrame(columns=["mes", "CENTRO_COSTO", "monto", "movimientos"])

    if _es_subtotal(categoria):
        mapa_signos = SUBTOTALES[categoria]
        lista_cats = ",".join(f"'{c}'" for c in mapa_signos)
        sql = f"""
            SELECT Subclasificacion_Final AS categoria, DATE_TRUNC('month', FECHA) AS mes,
                   CENTRO_COSTO, SUM({col}) AS monto, COUNT(*) AS movimientos
            FROM mayor_gyp_clasificado
            WHERE Empresa IN ({ph}) AND Subclasificacion_Final IN ({lista_cats})
              AND FECHA BETWEEN '{inicio}' AND '{fin}'
            GROUP BY 1, 2, 3
        """
        df = con.execute(sql).fetchdf()
        df.loc[df["categoria"].isin(CATEGORIAS_INGRESO), "monto"] *= -1
        df["signo"] = df["categoria"].map(mapa_signos)
        df["monto"] = df["monto"] * df["signo"]
        return df.groupby(["mes", "CENTRO_COSTO"], as_index=False).agg(
            monto=("monto", "sum"), movimientos=("movimientos", "sum")
        )

    sql = f"""
        SELECT DATE_TRUNC('month', FECHA) AS mes, CENTRO_COSTO,
               SUM({col}) AS monto, COUNT(*) AS movimientos
        FROM mayor_gyp_clasificado
        WHERE Empresa IN ({ph}) AND Subclasificacion_Final = ?
          AND FECHA BETWEEN '{inicio}' AND '{fin}'
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    df = con.execute(sql, [categoria]).fetchdf()
    if categoria in CATEGORIAS_INGRESO:
        df["monto"] = -df["monto"]
    return df


def top_movimientos(con, empresas: list, categoria: str, moneda: str,
                     centro_costo: str = None, mes: str = None, limite: int = 15) -> pd.DataFrame:
    col = _col_monto(moneda)
    ph = ",".join(f"'{e}'" for e in empresas)

    if _es_subtotal(categoria):
        lista_cats = ",".join(f"'{c}'" for c in SUBTOTALES[categoria])
        condiciones = [f"Empresa IN ({ph})", f"Subclasificacion_Final IN ({lista_cats})"]
        parametros = []
    else:
        condiciones = [f"Empresa IN ({ph})", "Subclasificacion_Final = ?"]
        parametros = [categoria]
    if centro_costo:
        condiciones.append("CENTRO_COSTO = ?")
        parametros.append(centro_costo)
    if mes:
        condiciones.append("DATE_TRUNC('month', FECHA) = ?")
        parametros.append(mes)
    where = " AND ".join(condiciones)

    sql = f"""
        SELECT FECHA, Empresa, Subclasificacion_Final AS categoria,
               CENTRO_COSTO, CUENTA_CONTABLE, REFERENCIA, {col} AS monto
        FROM mayor_gyp_clasificado
        WHERE {where}
        ORDER BY ABS({col}) DESC
        LIMIT {limite}
    """
    df = con.execute(sql, parametros).fetchdf()
    if not _es_subtotal(categoria) and categoria in CATEGORIAS_INGRESO:
        df["monto"] = -df["monto"]
    return df


def variacion_mensual(serie_mensual: pd.DataFrame) -> pd.DataFrame:
    if serie_mensual.empty or "mes" not in serie_mensual.columns:
        return pd.DataFrame(columns=["mes", "monto", "variacion_pct"])
    df = serie_mensual.groupby("mes", as_index=False)["monto"].sum().sort_values("mes")
    df["mes_anterior"] = df["monto"].shift(1)
    df["variacion_pct"] = ((df["monto"] - df["mes_anterior"]) / df["mes_anterior"].abs() * 100).round(1)
    return df[["mes", "monto", "variacion_pct"]]


def ventas_totales_mensual(con, empresas: list, moneda: str) -> pd.DataFrame:
    col = _col_monto(moneda)
    ph = ",".join(f"'{e}'" for e in empresas)
    sql = f"WITH {cte.cte_catalogo_expandido()}\n" + f"""
        SELECT DATE_TRUNC('month', m.FECHA) AS mes, -SUM(m.{col}) AS ventas
        FROM mayor_contable m
        JOIN catalogo_expandido c ON m.CUENTA_CONTABLE = c.cuenta AND m.Empresa = c.Empresa
        WHERE m.Empresa IN ({ph}) AND c.Clasificacion = 'B.Renta Bruta'
          AND LOWER(c.nombre_cuenta) LIKE '%venta%' AND c.cuenta LIKE '4%'
        GROUP BY 1
        ORDER BY 1
    """
    return con.execute(sql).fetchdf()


def gasto_sobre_ventas(con, empresas: list, categoria: str, moneda: str) -> pd.DataFrame:
    col = _col_monto(moneda)
    ph = ",".join(f"'{e}'" for e in empresas)
    inicio, fin = _rango_ultimos_12_meses(con, empresas)
    if inicio is None:
        return pd.DataFrame(columns=["mes", "gasto", "ventas", "pct_sobre_ventas"])

    if _es_subtotal(categoria):
        mapa_signos = SUBTOTALES[categoria]
        lista_cats = ",".join(f"'{c}'" for c in mapa_signos)
        sql = f"""
            SELECT Subclasificacion_Final AS categoria, DATE_TRUNC('month', FECHA) AS mes, SUM({col}) AS monto
            FROM mayor_gyp_clasificado
            WHERE Empresa IN ({ph}) AND Subclasificacion_Final IN ({lista_cats})
              AND FECHA BETWEEN '{inicio}' AND '{fin}'
            GROUP BY 1, 2
        """
        detalle_df = con.execute(sql).fetchdf()
        detalle_df.loc[detalle_df["categoria"].isin(CATEGORIAS_INGRESO), "monto"] *= -1
        detalle_df["signo"] = detalle_df["categoria"].map(mapa_signos)
        detalle_df["monto"] = detalle_df["monto"] * detalle_df["signo"]
        gasto = detalle_df.groupby("mes", as_index=False)["monto"].sum().rename(columns={"monto": "gasto"})
    else:
        sql = f"""
            SELECT DATE_TRUNC('month', FECHA) AS mes, SUM({col}) AS gasto
            FROM mayor_gyp_clasificado
            WHERE Empresa IN ({ph}) AND Subclasificacion_Final = ?
              AND FECHA BETWEEN '{inicio}' AND '{fin}'
            GROUP BY 1
            ORDER BY 1
        """
        gasto = con.execute(sql, [categoria]).fetchdf()
        if categoria in CATEGORIAS_INGRESO:
            gasto["gasto"] = -gasto["gasto"]

    ventas = ventas_totales_mensual(con, empresas, moneda)
    combinado = gasto.merge(ventas, on="mes", how="left")
    combinado["pct_sobre_ventas"] = (combinado["gasto"].abs() / combinado["ventas"].abs() * 100).round(2)
    return combinado


def real_vs_presupuesto(con, empresas: list, categoria: str, moneda: str) -> pd.DataFrame:
    """El presupuesto (tabla plana PRESUPUESTO2026.xlsx) sí tiene detalle
    por cuenta, así que aquí SÍ podemos dar Real vs. Presupuesto por
    categoría individual (a diferencia de la v3/Fabric, donde solo había
    presupuesto a nivel de Gastos Operativos total)."""
    col_real = _col_monto(moneda)
    col_ppto = "Monto USD" if moneda == "USD" else "Monto"
    ph = ",".join(f"'{e}'" for e in empresas)
    inicio, fin = _rango_ultimos_12_meses(con, empresas)
    if inicio is None:
        return pd.DataFrame(columns=["mes", "real_monto", "presupuesto_monto"])

    if _es_subtotal(categoria):
        mapa_signos = SUBTOTALES[categoria]
        lista_cats_final = ",".join(f"'{c}'" for c in mapa_signos)
        sql = f"""
            SELECT Subclasificacion_Final AS categoria, DATE_TRUNC('month', FECHA) AS mes, SUM({col_real}) AS monto
            FROM mayor_gyp_clasificado
            WHERE Empresa IN ({ph}) AND Subclasificacion_Final IN ({lista_cats_final})
              AND FECHA BETWEEN '{inicio}' AND '{fin}'
            GROUP BY 1, 2
        """
        detalle_df = con.execute(sql).fetchdf()
        detalle_df.loc[detalle_df["categoria"].isin(CATEGORIAS_INGRESO), "monto"] *= -1
        detalle_df["signo"] = detalle_df["categoria"].map(mapa_signos)
        detalle_df["monto"] = detalle_df["monto"] * detalle_df["signo"]
        real = detalle_df.groupby("mes", as_index=False)["monto"].sum().rename(columns={"monto": "real_monto"})

        lista_cats_2 = ",".join(f"'{c}'" for c in mapa_signos)
        sql_p = f"""
            SELECT DATE_TRUNC('month', p.Fecha) AS mes, SUM(p."{col_ppto}" * s.signo) AS presupuesto_monto
            FROM presupuesto p
            JOIN catalogo_gyp c ON p.Cuenta = c.cuenta AND p.Empresa = c.Empresa
            JOIN (SELECT * FROM (VALUES {",".join(f"('{k}', {v})" for k, v in mapa_signos.items())}) AS t(categoria, signo)) s
              ON c.Subclasificacion = s.categoria
            WHERE p.Empresa IN ({ph}) AND p.Fecha BETWEEN '{inicio}' AND '{fin}'
            GROUP BY 1
        """
        presupuesto = con.execute(sql_p).fetchdf()
    else:
        sql = f"""
            SELECT DATE_TRUNC('month', FECHA) AS mes, SUM({col_real}) AS real_monto
            FROM mayor_gyp_clasificado
            WHERE Empresa IN ({ph}) AND Subclasificacion_Final = ?
              AND FECHA BETWEEN '{inicio}' AND '{fin}'
            GROUP BY 1
            ORDER BY 1
        """
        real = con.execute(sql, [categoria]).fetchdf()
        if categoria in CATEGORIAS_INGRESO:
            real["real_monto"] = -real["real_monto"]

        sql_p = f"""
            SELECT DATE_TRUNC('month', p.Fecha) AS mes, SUM(p."{col_ppto}") AS presupuesto_monto
            FROM presupuesto p
            JOIN catalogo_gyp c ON p.Cuenta = c.cuenta AND p.Empresa = c.Empresa
            WHERE p.Empresa IN ({ph}) AND c.Subclasificacion = ?
              AND p.Fecha BETWEEN '{inicio}' AND '{fin}'
            GROUP BY 1
        """
        presupuesto = con.execute(sql_p, [categoria]).fetchdf()

    return real.merge(presupuesto, on="mes", how="outer").sort_values("mes")
