"""
Proyecto v4 - Dashboard principal GYP, en DuckDB (archivos locales),
incorporando todas las mejoras de la v3: signo de cuentas de ingreso,
subtotales calculados (Gastos Operativos, Ganancia Operativa, Semi Neto),
y el mapeo real por empresa (vía 09_cte_clasificacion.py).
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
CATEGORIAS_EXCLUIDAS_DETALLE = [
    '14.1.Perdida Cambiaria', '14.2.Gastos Extraordinarios', '14.3.Reservas Eventuales',
    '14.Otros Egresos', '15.1.Bancos', '15.2.Otros Prestamos', '15.Intereses',
    '16.Depreciaicion', '16.Depreciación', '17.1.Corriente', '17.ISLR',
]

CATEGORIAS_DASHBOARD = CATEGORIAS_RENTA_BRUTA + CATEGORIAS_GASTOS_OPERATIVOS + [
    "Gastos Operativos", "Ganancia Operativa", "Semi Neto",
]

# Empresa -> categorías donde el mayor transaccional YA NO trae el detalle
# necesario (ver 15_cargar_resumen_gyp.py) y hay que usar el valor real
# directo de la tabla resumen_gyp_real en su lugar.
CATEGORIAS_SOLO_RESUMEN = {
    "Cofersa": ["01.Margen"],
}

EMPRESAS_POR_PAIS = {
    "Colombia": ["Mundial"],
    "Costa Rica": ["Cofersa", "Prisma CR"],
    "Venezuela": ["Febeca", "Beval", "Prisma", "Sillaca"],
}


def _pivotear_series(df_mensual: pd.DataFrame, col_categoria: str, meses_deseados: int = 13) -> pd.DataFrame:
    """
    Ancla el 'mes de referencia' por CANTIDAD de movimientos (no por
    monto, que es inestable), acotado a los últimos 36 meses para no
    dejar que un mes viejo con mucho volumen gane el umbral, y sin
    pasarse de la fecha real de hoy (evita meses "fantasma" fechados a
    futuro).
    """
    if df_mensual.empty:
        return pd.DataFrame(columns=[col_categoria, "monto_actual", "var_interanual_pct", "tendencia_12m"])

    hoy = pd.Timestamp.now().normalize().replace(day=1)
    conteo_por_mes = df_mensual.groupby("mes")["conteo"].sum()
    conteo_por_mes = conteo_por_mes[conteo_por_mes.index <= hoy]
    if conteo_por_mes.empty:
        return pd.DataFrame(columns=[col_categoria, "monto_actual", "var_interanual_pct", "tendencia_12m"])

    fecha_max_absoluta = conteo_por_mes.index.max()
    ventana_reciente = conteo_por_mes[conteo_por_mes.index >= fecha_max_absoluta - pd.DateOffset(months=36)]
    umbral = ventana_reciente.median() * 0.60
    mes_referencia = ventana_reciente[ventana_reciente >= umbral].index.max()

    tabla = df_mensual.pivot_table(index=col_categoria, columns="mes", values="valor", aggfunc="sum", fill_value=0.0)
    todas_las_columnas = sorted(tabla.columns)
    columnas_hasta_referencia = [c for c in todas_las_columnas if c <= mes_referencia]
    meses_ordenados = columnas_hasta_referencia[-meses_deseados:]
    tabla = tabla.reindex(columns=meses_ordenados, fill_value=0.0)

    filas = []
    for categoria, serie in tabla.iterrows():
        valores = serie.tolist()
        if len(valores) >= 13:
            actual, hace_un_anio, tendencia = valores[-1], valores[-13], valores[-12:]
        else:
            actual = valores[-1] if valores else 0.0
            hace_un_anio = valores[0] if valores else 0.0
            tendencia = valores[-12:] if valores else [0.0]
        var_pct = None if hace_un_anio == 0 else round(100.0 * (actual - hace_un_anio) / abs(hace_un_anio), 1)
        filas.append({col_categoria: categoria, "monto_actual": round(actual, 2),
                       "var_interanual_pct": var_pct, "tendencia_12m": tendencia})

    return pd.DataFrame(filas).sort_values("monto_actual", key=abs, ascending=False).reset_index(drop=True)


def dashboard_gyp(con, empresas: list, moneda: str) -> pd.DataFrame:
    col_monto = "MONTO_DOLAR_NETO" if moneda == "USD" else "MONTO_LOCAL_NETO"
    placeholders = ",".join(f"'{e}'" for e in empresas)

    sql = f"""
        SELECT Empresa, Subclasificacion_Final AS categoria, DATE_TRUNC('month', FECHA) AS mes,
               SUM({col_monto}) AS valor,
               SUM(CASE WHEN Origen_Datos = 'ERP' THEN 1 ELSE 0 END) AS conteo
        FROM mayor_gyp_clasificado
        WHERE Empresa IN ({placeholders})
          AND Subclasificacion_Final SIMILAR TO '[0-9].*'
        GROUP BY 1, 2, 3
    """
    df = con.execute(sql).fetchdf()
    df.loc[df["categoria"].isin(CATEGORIAS_INGRESO), "valor"] *= -1

    # Reemplazar, empresa por empresa, las categorías donde el mayor
    # transaccional ya no alcanza (ver CATEGORIAS_SOLO_RESUMEN) por el
    # valor real directo de resumen_gyp_real.
    for empresa, categorias in CATEGORIAS_SOLO_RESUMEN.items():
        if empresa not in empresas or not categorias:
            continue
        lista_cats = ",".join(f"'{c}'" for c in categorias)
        df = df[~((df["Empresa"] == empresa) & (df["categoria"].isin(categorias)))]
        resumen = con.execute(f"""
            SELECT Empresa, categoria, mes, valor_usd AS valor
            FROM resumen_gyp_real
            WHERE Empresa = '{empresa}' AND categoria IN ({lista_cats})
        """).fetchdf()
        if moneda != "USD":
            resumen["valor"] = None  # el resumen real solo viene en USD por ahora
        resumen["conteo"] = 0
        df = pd.concat([df, resumen], ignore_index=True)

    df = df.drop(columns=["Empresa"]).groupby(["categoria", "mes"], as_index=False).agg(
        valor=("valor", "sum"), conteo=("conteo", "sum")
    )

    renta_bruta = df[df["categoria"].isin(CATEGORIAS_RENTA_BRUTA)].groupby("mes")["valor"].sum()
    gastos_operativos = df[df["categoria"].isin(CATEGORIAS_GASTOS_OPERATIVOS)].groupby("mes")["valor"].sum()
    resta_semi_neto = df[df["categoria"].isin(CATEGORIAS_SEMI_NETO_RESTA)].groupby("mes")["valor"].sum()
    ganancia_operativa = renta_bruta.subtract(gastos_operativos, fill_value=0)
    semi_neto = ganancia_operativa.subtract(resta_semi_neto, fill_value=0)
    conteo_total_por_mes = df.groupby("mes")["conteo"].sum()

    subtotales = []
    for nombre, serie in [("Gastos Operativos", gastos_operativos),
                          ("Ganancia Operativa", ganancia_operativa),
                          ("Semi Neto", semi_neto)]:
        for mes, valor in serie.items():
            subtotales.append({"categoria": nombre, "mes": mes, "valor": valor,
                                "conteo": conteo_total_por_mes.get(mes, 0)})
    df_subtotales = pd.DataFrame(subtotales)

    df_detalle = df[~df["categoria"].isin(CATEGORIAS_EXCLUIDAS_DETALLE)]
    df_final = pd.concat([df_detalle, df_subtotales], ignore_index=True)
    return _pivotear_series(df_final, "categoria")
