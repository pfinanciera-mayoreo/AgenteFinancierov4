"""
Proyecto v2 - Convierte el manual de Gastos Generales (docx) en una tabla de
referencia por SQL.

OJO: la numeración de este manual (ej. "711.01", subcuenta "-1001") NO
coincide con el formato de cuenta que usan los mayores reales (ni el de
puntos "7.1.1.09.1.900" ni el de guiones "1-01-01-01-00"). Intentar mapear
código-a-código sería adivinar y podría dar información cruzada de forma
silenciosa. Por eso esta tabla se diseñó para consultarse por PALABRA CLAVE
(ILIKE sobre nombre_cuenta o descripcion), como contexto adicional de
negocio — no como llave de JOIN exacta con mayor_contable.
"""
import re
import docx
import duckdb

DB_PATH = "data/financiero_v2.duckdb"
ARCHIVO_DOCX = "1_1_9__Gastos_Generales.docx"

PATRON_PRINCIPAL = re.compile(r'^(\d{3}\.\d{2})\s*[-–]\s*(.+)$')
PATRON_SUBCUENTA = re.compile(r'^-(\d{4})\s*[-–]\s*(.+)$')


def parsear_manual():
    d = docx.Document(ARCHIVO_DOCX)
    registros = []

    codigo_principal, nombre_principal = None, None
    codigo_sub, nombre_sub = None, None
    descripcion_actual = []

    def flush():
        if codigo_sub is not None:
            registros.append({
                "codigo_referencia": f"{codigo_principal}.{codigo_sub}",
                "cuenta_principal": f"{codigo_principal} - {nombre_principal}",
                "nombre_subcuenta": nombre_sub,
                "descripcion": " ".join(descripcion_actual).strip(),
            })
        elif codigo_principal is not None and descripcion_actual:
            # Texto que cae directo bajo la cuenta principal, sin subcuenta.
            registros.append({
                "codigo_referencia": codigo_principal,
                "cuenta_principal": f"{codigo_principal} - {nombre_principal}",
                "nombre_subcuenta": None,
                "descripcion": " ".join(descripcion_actual).strip(),
            })

    for p in d.paragraphs:
        t = p.text.strip()
        if not t:
            continue

        m_principal = PATRON_PRINCIPAL.match(t)
        m_sub = PATRON_SUBCUENTA.match(t)

        if m_principal:
            flush()
            codigo_principal, nombre_principal = m_principal.group(1), m_principal.group(2)
            codigo_sub, nombre_sub = None, None
            descripcion_actual = []
        elif m_sub:
            flush()
            codigo_sub, nombre_sub = m_sub.group(1), m_sub.group(2)
            descripcion_actual = []
        else:
            descripcion_actual.append(t)

    flush()
    return registros


if __name__ == "__main__":
    registros = parsear_manual()
    print(f"Registros extraídos del manual: {len(registros)}")
    print("Ejemplo:", registros[2] if len(registros) > 2 else registros[0])

    con = duckdb.connect(DB_PATH)
    import pandas as pd
    df = pd.DataFrame(registros)
    con.execute("CREATE OR REPLACE TABLE manual_cuentas_gastos AS SELECT * FROM df")
    print(f"\nTabla manual_cuentas_gastos creada con {len(df):,} filas.")
    con.close()
