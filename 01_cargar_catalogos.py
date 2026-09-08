"""
Proyecto v2 - Cargador de catálogos desde Dicionario_Global_Final_.xlsx

Este diccionario tiene 3 hojas:
  - GYP:    catálogo de cuentas de Estado de Resultados
  - Balance: catálogo de cuentas de Balance General
  - FC:     categorías de Flujo de Caja (tabla chica de referencia)

Detalle importante de negocio (confirmado con el usuario):
  - Empresa='venezuela' en GYP/Balance es una PLANTILLA GENÉRICA que aplica
    a las 4 empresas venezolanas: Febeca, Beval, Prisma, Sillaca. Hay que
    EXPANDIR cada una de esas filas en 4 filas (una por empresa).
  - Empresa='mundial' / 'cofersa' ya vienen específicas para esa empresa,
    se cargan tal cual (mezclan cuentas con guion -las reales- y unas pocas
    con punto -genéricas de "Carga Inicial"-, ambas son válidas).
  - Empresa='olo' se DESCARTA por instrucción del usuario (empresa de Costa
    Rica fuera de alcance por ahora).
"""
import duckdb
import pandas as pd
import openpyxl

DB_PATH = "data/financiero_v2.duckdb"
DICCIONARIO_XLSX = "Dicionario_Global_Final_.xlsx"

EMPRESAS_VENEZUELA = ["Febeca", "Beval", "Prisma", "Sillaca"]


def normalizar_empresa(valor: str) -> str:
    """Pasa 'FEBECA'/'febeca'/'Febeca' -> 'Febeca', consistente en todo el proyecto."""
    mapa = {
        "febeca": "Febeca", "beval": "Beval", "prisma": "Prisma",
        "sillaca": "Sillaca", "mundial": "Mundial", "cofersa": "Cofersa",
    }
    if valor is None:
        return valor
    return mapa.get(str(valor).strip().lower(), valor)


def expandir_venezuela(df: pd.DataFrame, col_empresa: str) -> pd.DataFrame:
    """
    Por cada fila con Empresa='venezuela' (sin importar mayúsculas), crea 4
    copias -una por cada empresa venezolana-, y descarta las de 'olo'.
    Las filas de 'mundial'/'cofersa' se devuelven normalizadas tal cual.
    """
    df = df.copy()
    df[col_empresa] = df[col_empresa].astype(str).str.strip()

    es_venezuela = df[col_empresa].str.lower() == "venezuela"
    es_olo = df[col_empresa].str.lower() == "olo"

    filas_venezuela = df[es_venezuela]
    filas_otras = df[~es_venezuela & ~es_olo].copy()
    filas_otras[col_empresa] = filas_otras[col_empresa].apply(normalizar_empresa)

    expandidas = []
    for empresa_ve in EMPRESAS_VENEZUELA:
        copia = filas_venezuela.copy()
        copia[col_empresa] = empresa_ve
        expandidas.append(copia)

    resultado = pd.concat([filas_otras] + expandidas, ignore_index=True)
    return resultado


def cargar_gyp(con):
    df = pd.read_excel(DICCIONARIO_XLSX, sheet_name="GYP")
    df = expandir_venezuela(df, "Empresa")
    con.execute("CREATE OR REPLACE TABLE catalogo_gyp AS SELECT * FROM df")
    print(f"catalogo_gyp: {len(df):,} filas (tras expandir Venezuela y descartar 'olo')")
    print("  Por empresa:")
    print(df["Empresa"].value_counts().to_string())


def cargar_balance(con):
    df = pd.read_excel(DICCIONARIO_XLSX, sheet_name="Balance")
    df = expandir_venezuela(df, "empresa")
    con.execute("CREATE OR REPLACE TABLE catalogo_balance AS SELECT * FROM df")
    print(f"\ncatalogo_balance: {len(df):,} filas")
    print("  Por empresa:")
    print(df["empresa"].value_counts().to_string())


def cargar_flujo_caja(con):
    df = pd.read_excel(DICCIONARIO_XLSX, sheet_name="FC")
    con.execute("CREATE OR REPLACE TABLE catalogo_flujo_caja AS SELECT * FROM df")
    print(f"\ncatalogo_flujo_caja: {len(df):,} filas")


if __name__ == "__main__":
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = duckdb.connect(DB_PATH)
    cargar_gyp(con)
    cargar_balance(con)
    cargar_flujo_caja(con)
    con.close()
    print(f"\nListo: {DB_PATH}")
