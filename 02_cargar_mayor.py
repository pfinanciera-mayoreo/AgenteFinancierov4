"""
Proyecto v2 - Cargador del mayor contable (5 empresas: Mundial, Prisma, Beval,
Cofersa, Febeca — Sillaca no tiene mayor transaccional en este envío).

2 problemas de formato reales, encontrados al inspeccionar los datos:

1. NÚMEROS EN FORMATO LATINO: "1.025.718,15" en vez de "1025718.15"
   (punto = separador de miles, coma = separador decimal). Si se castea
   directo a número, sale mal (ej. "12.613,44" se leería como 12.613,
   perdiendo los decimales reales). Hay que quitar los puntos de miles y
   cambiar la coma decimal por un punto ANTES de convertir a número.

2. FECHAS INCOMPLETAS: ~13% de las filas traen FECHA='2026-01' (sin día)
   en vez de '2026-01-01'. Hay que rellenar con '-01' cuando falte el día.
"""
import os
import duckdb

DB_PATH = "data/financiero_v2.duckdb"

EMPRESA_A_PAIS = {
    "Mundial": "Colombia", "Cofersa": "Costa Rica",
    "Febeca": "Venezuela", "Prisma": "Venezuela",
    "Sillaca": "Venezuela", "Beval": "Venezuela",
}

ARCHIVOS_MAYOR = {
    "Mundial": "mayor_mundial.txt",
    "Prisma": "mayor_prisma.txt",
    "Beval": "mayor_beval.txt",
    "Cofersa": "mayor_cofersa.txt",
    "Febeca": "mayor_febeca.txt",
    "Sillaca": "mayor_sillaca.txt",
}

# Expresión SQL reutilizable: convierte un texto en formato latino a DOUBLE.
# replace(col, '.', '')  -> quita separadores de miles
# replace(..., ',', '.') -> convierte la coma decimal en punto
# NULLIF(..., '')        -> evita error si queda una cadena vacía
def _sql_numero_latino(col: str) -> str:
    return f"TRY_CAST(NULLIF(REPLACE(REPLACE({col}, '.', ''), ',', '.'), '') AS DOUBLE)"


# Expresión SQL: si FECHA tiene menos de 10 caracteres (ej. '2026-01'),
# le agrega '-01' para que quede '2026-01-01' y sí se pueda castear a DATE.
def _sql_fecha_completa(col: str) -> str:
    return f"TRY_CAST(CASE WHEN LENGTH({col}) < 10 THEN {col} || '-01' ELSE {col} END AS DATE)"


def cargar_una_empresa(con, empresa: str, archivo: str):
    if not os.path.exists(archivo):
        print(f"  ⚠️  {archivo} no encontrado — se salta.")
        return False

    pais = EMPRESA_A_PAIS[empresa]
    debito_local = _sql_numero_latino("DEBITO_LOCAL")
    credito_local = _sql_numero_latino("CREDITO_LOCAL")
    debito_dolar = _sql_numero_latino("DEBITO_DOLAR")
    credito_dolar = _sql_numero_latino("CREDITO_DOLAR")

    select_normalizado = f"""
        SELECT
            ASIENTO, CONSECUTIVO, NIT, CENTRO_COSTO, CUENTA_CONTABLE,
            FUENTE, REFERENCIA,
            {debito_local} AS DEBITO_LOCAL,
            {credito_local} AS CREDITO_LOCAL,
            {debito_dolar} AS DEBITO_DOLAR,
            {credito_dolar} AS CREDITO_DOLAR,
            {_sql_fecha_completa("FECHA")} AS FECHA,
            '{empresa}' AS Empresa,
            '{pais}' AS Pais,
            COALESCE({debito_dolar}, 0) - COALESCE({credito_dolar}, 0) AS MONTO_DOLAR_NETO,
            COALESCE({debito_local}, 0) - COALESCE({credito_local}, 0) AS MONTO_LOCAL_NETO
        FROM read_csv('{archivo}', delim='|', header=True, quote='"', all_varchar=True)
    """

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS mayor_contable AS {select_normalizado} WHERE FALSE
    """)
    con.execute(f"INSERT INTO mayor_contable {select_normalizado}")

    n = con.execute("SELECT COUNT(*) FROM mayor_contable WHERE Empresa = ?", [empresa]).fetchone()[0]
    print(f"  ✅ {empresa}: {n:,} filas cargadas desde {archivo}")
    return True


if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS mayor_contable")

    print("Cargando mayor contable v2...")
    for empresa, archivo in ARCHIVOS_MAYOR.items():
        cargar_una_empresa(con, empresa, archivo)

    total = con.execute("SELECT COUNT(*) FROM mayor_contable").fetchone()[0]
    print(f"\nTotal mayor_contable: {total:,} filas")

    nulos = con.execute("""
        SELECT COUNT(*) FROM mayor_contable
        WHERE MONTO_DOLAR_NETO IS NULL OR MONTO_LOCAL_NETO IS NULL OR FECHA IS NULL
    """).fetchone()[0]
    estado = "✅" if nulos == 0 else "⚠️"
    print(f"{estado} Filas con monto o fecha en NULL tras la limpieza: {nulos:,}")

    con.close()
