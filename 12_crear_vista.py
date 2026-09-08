"""
Proyecto v4 - Crea la vista PERSISTENTE mayor_gyp_clasificado en la base
de datos, para que tanto el agente de IA (que solo escribe SQL normal
contra tablas/vistas) como el dashboard puedan usarla directamente sin
necesidad de anteponer ningún CTE.

Corre esto después de cargar mayor_contable, asientos_planificacion y
catalogo_gyp (ver 06_cargar_todo.py).
"""
import duckdb
from importlib import import_module

cte = import_module("09_cte_clasificacion")

DB_PATH = "data/financiero_v2.duckdb"


def crear_vista(con):
    sql = "CREATE OR REPLACE VIEW mayor_gyp_clasificado AS " + cte.cte_mayor_gyp_clasificado() + " SELECT * FROM mayor_gyp_clasificado"
    con.execute(sql)


if __name__ == "__main__":
    con = duckdb.connect(DB_PATH)
    crear_vista(con)
    print("Vista 'mayor_gyp_clasificado' creada/actualizada.")

    r = con.execute("""
        SELECT Empresa, COUNT(*) AS movimientos, SUM(MONTO_DOLAR_NETO) AS usd
        FROM mayor_gyp_clasificado
        WHERE Subclasificacion_Final = '18.Logistica'
          AND FECHA BETWEEN '2025-01-01' AND '2026-07-31'
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    print("\nMovimientos de 18.Logistica por empresa (ene25-jul26):")
    print(r.to_string(index=False))
    con.close()
