"""
Proyecto v2 - Script maestro. Corre los 5 cargadores en orden y hace un
reporte de validación final. Este es el único script que necesitas correr
para (re)construir la base completa.
"""
import subprocess
import sys

SCRIPTS = [
    "01_cargar_catalogos.py",
    "02_cargar_mayor.py",
    "03_cargar_balance.py",
    "04_cargar_planificacion.py",
    "05_cargar_manual_cuentas.py",
    "13_cargar_presupuesto.py",
    "12_crear_vista.py",
]

DB_PATH = "data/financiero_v2.duckdb"


def correr_todo():
    for script in SCRIPTS:
        print(f"\n{'='*70}\n▶ {script}\n{'='*70}")
        resultado = subprocess.run([sys.executable, script])
        if resultado.returncode != 0:
            print(f"\n🛑 {script} falló — deteniendo aquí.")
            sys.exit(1)


def validar():
    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    print(f"\n{'='*70}\nREPORTE DE VALIDACIÓN FINAL\n{'='*70}")

    tablas = ["catalogo_gyp", "catalogo_balance", "catalogo_flujo_caja",
              "mayor_contable", "saldos_balance", "asientos_planificacion",
              "manual_cuentas_gastos"]
    for t in tablas:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n:,} filas")

    # Cobertura del catálogo GYP sobre el mayor real (por empresa)
    print("\nCobertura de catalogo_gyp sobre mayor_contable, por empresa:")
    r = con.execute("""
        SELECT m.Empresa,
               COUNT(DISTINCT m.CUENTA_CONTABLE) AS cuentas_en_mayor,
               COUNT(DISTINCT c.cuenta) AS cuentas_con_match
        FROM mayor_contable m
        LEFT JOIN catalogo_gyp c ON m.CUENTA_CONTABLE = c.cuenta AND m.Empresa = c.Empresa
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    print(r.to_string(index=False))

    con.close()


if __name__ == "__main__":
    correr_todo()
    validar()
