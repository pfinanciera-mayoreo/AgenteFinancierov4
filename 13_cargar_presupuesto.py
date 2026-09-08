"""
Proyecto v2 - Cargador de Presupuesto (reincorporado desde la v1, mismo
archivo PRESUPUESTO2026.xlsx). Se une a catalogo_gyp por Cuenta+Empresa
para poder comparar Real vs. Presupuesto por categoría.

Cobertura verificada: 47 de 51 cuentas presupuestadas tienen match en el
catálogo v2 (92%). Las 4 sin match probablemente son cuentas que cambiaron
de código entre el diccionario viejo (v1) y el nuevo (Dicionario_Global_Final).
"""
import os
import duckdb
import pandas as pd

DB_PATH = "data/financiero_v2.duckdb"
ARCHIVO = "PRESUPUESTO2026.xlsx"

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    df = pd.read_excel(ARCHIVO)

    con = duckdb.connect(DB_PATH)
    con.execute("CREATE OR REPLACE TABLE presupuesto AS SELECT * FROM df")

    n = con.execute("SELECT COUNT(*) FROM presupuesto").fetchone()[0]
    print(f"presupuesto: {n:,} filas")

    r = con.execute("""
        SELECT COUNT(DISTINCT p.Cuenta) AS cuentas_presupuesto,
               COUNT(DISTINCT c.cuenta) AS con_match
        FROM presupuesto p LEFT JOIN catalogo_gyp c ON p.Cuenta = c.cuenta AND p.Empresa = c.Empresa
    """).fetchone()
    print(f"Cobertura del catálogo v2: {r[1]}/{r[0]} cuentas con match")
    con.close()
