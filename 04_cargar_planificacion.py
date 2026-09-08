"""
Proyecto v2 - Cargador de asientos de planificación financiera.

Estos son AJUSTES DE PRESENTACIÓN que NO están en el ERP (no forman parte del
mayor_contable). Se guardan en una tabla SEPARADA a propósito: el agente debe
decir explícitamente cuándo un número incluye estos ajustes, en vez de
mezclarlos en silencio con el mayor real.

Ya trae "Movimiento_Dolar" y "Movimiento_Local" precalculados (verificado:
coincide exacto con Débito - Crédito), así que los usamos directo sin
recalcular.

La columna 'pais' de este archivo NO es confiable (mezcla nombres de empresa
donde debería decir país), así que la ignoramos y usamos nuestro propio mapeo
Empresa -> País, igual que en el resto del proyecto.
"""
import os
import duckdb
import pandas as pd
import numpy as np

DB_PATH = "data/financiero_v2.duckdb"
ARCHIVO = "asientos_de_planificacion.xlsx"

EMPRESA_A_PAIS = {
    "Mundial": "Colombia", "Cofersa": "Costa Rica",
    "Febeca": "Venezuela", "Prisma": "Venezuela",
    "Sillaca": "Venezuela", "Beval": "Venezuela",
}


def normalizar_empresa(valor):
    mapa = {
        "febeca": "Febeca", "beval": "Beval", "prisma": "Prisma",
        "sillaca": "Sillaca", "mundial": "Mundial", "cofersa": "Cofersa",
    }
    if pd.isna(valor):
        return valor
    return mapa.get(str(valor).strip().lower(), valor)


def limpiar_numero(x):
    """Convierte '-' (placeholder de 'sin valor' en este archivo) y vacíos en
    0.0, y el resto a float. Sin esto, la columna queda mezclada texto/número
    y DuckDB la guarda entera como VARCHAR (no se puede sumar)."""
    if pd.isna(x) or x == "-":
        return 0.0
    return float(x)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    df = pd.read_excel(ARCHIVO)
    df["Empresa"] = df["Empresa"].apply(normalizar_empresa)
    df["Pais"] = df["Empresa"].map(EMPRESA_A_PAIS)
    df["Movimiento_Dolar"] = df["Movimiento_Dolar"].apply(limpiar_numero)
    df["Movimiento_Local"] = df["Movimiento_Local"].apply(limpiar_numero)

    # Nos quedamos con las columnas relevantes, con nombres consistentes al
    # resto del proyecto (MONTO_DOLAR_NETO / MONTO_LOCAL_NETO).
    columnas = {
        "ASIENTO": "ASIENTO", "CUENTA_CONTABLE": "CUENTA_CONTABLE",
        "REFERENCIA": "REFERENCIA", "CENTRO_COSTO": "CENTRO_COSTO",
        "FECHA": "FECHA", "Empresa": "Empresa", "Pais": "Pais",
        "Movimiento_Dolar": "MONTO_DOLAR_NETO",
        "Movimiento_Local": "MONTO_LOCAL_NETO",
    }
    df_final = df[list(columnas.keys())].rename(columns=columnas)

    con = duckdb.connect(DB_PATH)
    con.execute("CREATE OR REPLACE TABLE asientos_planificacion AS SELECT * FROM df_final")

    n = con.execute("SELECT COUNT(*) FROM asientos_planificacion").fetchone()[0]
    print(f"asientos_planificacion: {n:,} filas")
    print(con.execute("SELECT Empresa, COUNT(*), MIN(FECHA), MAX(FECHA) FROM asientos_planificacion GROUP BY 1").fetchdf())

    nulos_pais = con.execute("SELECT COUNT(*) FROM asientos_planificacion WHERE Pais IS NULL").fetchone()[0]
    estado = "✅" if nulos_pais == 0 else "⚠️"
    print(f"{estado} Filas sin País asignado (Empresa no reconocida): {nulos_pais}")

    con.close()
