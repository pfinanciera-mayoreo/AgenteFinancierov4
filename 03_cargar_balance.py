"""
Proyecto v2 - Cargador de saldos de Balance General (balance_mayoreo_*.txt).

A diferencia del mayor (transacción por transacción), estos archivos ya
traen el SALDO agregado por cuenta y mes: Mov_Local, MOV_DOLAR (movimiento
del mes) y Balance_Final / Balance_Final_Dolar (saldo acumulado a esa fecha).

La columna Empresa YA viene dentro de cada archivo (confirmado al inspeccionar:
cada archivo trae una sola empresa, ya en minúsculas) — no hace falta adivinar
por el nombre del archivo.
"""
import os
import duckdb

DB_PATH = "data/financiero_v2.duckdb"

ARCHIVOS_BALANCE = [
    "balance_mayoreo_mundial_prueba.txt",
    "balance_mayoreo_prs_prueba.txt",
    "balance_mayoreo_mb_prueba.txt",
    "balance_mayoreo_fb_prueba.txt",
    "balance_mayoreo_sc_prueba.txt",
    "balance_mayoreo_cofersa_prueba.txt",
]


def normalizar_empresa_sql() -> str:
    return """
        CASE lower(TRIM(Empresa))
            WHEN 'febeca' THEN 'Febeca' WHEN 'beval' THEN 'Beval'
            WHEN 'prisma' THEN 'Prisma' WHEN 'sillaca' THEN 'Sillaca'
            WHEN 'mundial' THEN 'Mundial' WHEN 'cofersa' THEN 'Cofersa'
            ELSE Empresa
        END
    """


def _sql_numero_latino(col: str) -> str:
    """Igual que en 02_cargar_mayor.py: '1.025.718,15' -> 1025718.15"""
    return f"TRY_CAST(NULLIF(REPLACE(REPLACE({col}, '.', ''), ',', '.'), '') AS DOUBLE)"


if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS saldos_balance")

    print("Cargando saldos de Balance General v2...")
    empresa_norm = normalizar_empresa_sql()
    primero = True
    for archivo in ARCHIVOS_BALANCE:
        if not os.path.exists(archivo):
            print(f"  ⚠️  {archivo} no encontrado — se salta.")
            continue
        select_sql = f"""
            SELECT CUENTA_CONTABLE, TRY_CAST(FECHA AS DATE) AS FECHA, {empresa_norm} AS Empresa,
                   {_sql_numero_latino("Mov_Local")} AS Mov_Local,
                   {_sql_numero_latino("MOV_DOLAR")} AS Mov_Dolar,
                   {_sql_numero_latino("Balance_Final")} AS Balance_Final,
                   {_sql_numero_latino("Balance_Final_Dolar")} AS Balance_Final_Dolar
            FROM read_csv('{archivo}', delim='|', header=True, quote='"', all_varchar=True)
        """
        if primero:
            con.execute(f"CREATE TABLE saldos_balance AS {select_sql}")
            primero = False
        else:
            con.execute(f"INSERT INTO saldos_balance {select_sql}")
        n = con.execute(f"""
            SELECT COUNT(*) FROM read_csv('{archivo}', delim='|', header=True, quote='"', all_varchar=True)
        """).fetchone()[0]
        print(f"  ✅ {archivo}: {n:,} filas")

    total = con.execute("SELECT COUNT(*) FROM saldos_balance").fetchone()[0]
    print(f"\nTotal saldos_balance: {total:,} filas")
    print(con.execute("SELECT Empresa, COUNT(*), MIN(FECHA), MAX(FECHA) FROM saldos_balance GROUP BY 1").fetchdf())
    con.close()
