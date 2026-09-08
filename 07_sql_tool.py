"""
Día 2 - Herramienta SQL con guardarraíles.

Esta es la función que el agente de Claude va a poder "llamar" (tool use) para
consultar la base de datos. Como el agente genera el SQL automáticamente a partir
de lenguaje natural, NUNCA debemos confiar ciegamente en ese SQL: por eso hay 3
capas de protección independientes (si una falla, las otras igual detienen algo
peligroso):

  Capa 1 (texto):     revisamos el texto del SQL antes de tocar la base de datos.
                       Bloquea palabras peligrosas (DROP, DELETE, etc.) y exige
                       que sea una sola sentencia que empiece con SELECT.
  Capa 2 (conexión):  abrimos DuckDB en modo read_only=True. Aunque algo se
                       cuele en la capa 1, el motor de la base de datos mismo
                       rechaza cualquier escritura.
  Capa 3 (límite):    forzamos un LIMIT máximo de filas devueltas, para nunca
                       mandarle al modelo miles de filas crudas (regla del
                       proyecto: los resultados deben venir agregados).
"""
import re
import duckdb

DB_PATH = "data/financiero_v2.duckdb"
LIMIT_MAXIMO_FILAS = 1000

# Palabras que jamás deben aparecer en el SQL que ejecuta el agente.
# Se comparan como palabras completas (word boundaries) para no bloquear por
# accidente columnas que solo contengan estas letras (ej. una columna llamada
# "updated_at" no debe disparar el bloqueo de "UPDATE").
PALABRAS_PROHIBIDAS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE",
    "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT", "PRAGMA",
    "INSTALL", "LOAD", "CALL", "GRANT", "REVOKE",
]


class SQLNoPermitidoError(Exception):
    """Se lanza cuando el SQL propuesto no cumple los guardarraíles."""
    pass


def validar_sql(query: str) -> str:
    """
    Revisa el texto del SQL antes de ejecutarlo. Lanza SQLNoPermitidoError si
    encuentra algo no permitido. Si todo está bien, devuelve el SQL limpio.
    """
    sql = query.strip()

    if not sql:
        raise SQLNoPermitidoError("La consulta viene vacía.")

    # Quitamos un ; final si lo trae, pero si hay un ; en medio del texto
    # (además del final) significa que son VARIAS sentencias -> lo bloqueamos.
    sql_sin_punto_final = sql[:-1] if sql.endswith(";") else sql
    if ";" in sql_sin_punto_final:
        raise SQLNoPermitidoError(
            "Solo se permite UNA sentencia SQL por consulta (se detectó un ';' extra)."
        )
    sql = sql_sin_punto_final

    # Debe empezar con SELECT o WITH (WITH es válido para CTEs: "WITH tmp AS (...) SELECT ...")
    primera_palabra = sql.strip().split(None, 1)[0].upper()
    if primera_palabra not in ("SELECT", "WITH"):
        raise SQLNoPermitidoError(
            f"Solo se permiten consultas SELECT. Esta consulta empieza con '{primera_palabra}'."
        )

    # Buscamos palabras prohibidas como palabras completas, sin importar mayúsc/minúsc.
    sql_upper = sql.upper()
    for palabra in PALABRAS_PROHIBIDAS:
        if re.search(rf"\b{palabra}\b", sql_upper):
            raise SQLNoPermitidoError(
                f"La consulta contiene la palabra no permitida: '{palabra}'."
            )

    return sql


def agregar_limite_si_falta(sql: str, limite: int = LIMIT_MAXIMO_FILAS) -> str:
    """
    Si el SQL no trae ya un LIMIT, le agregamos uno al final. Si trae un LIMIT
    más grande que el máximo permitido, lo recortamos al máximo.
    """
    match = re.search(r"\bLIMIT\s+(\d+)\b", sql, re.IGNORECASE)
    if match:
        limite_pedido = int(match.group(1))
        if limite_pedido > limite:
            sql = sql[:match.start()] + f"LIMIT {limite}" + sql[match.end():]
        return sql
    return f"{sql}\nLIMIT {limite}"


def ejecutar_sql_seguro(query: str) -> dict:
    """
    Punto de entrada único que va a usar el agente. Devuelve SIEMPRE un dict,
    nunca lanza una excepción hacia afuera: si algo sale mal, el error va
    dentro del dict para que el propio modelo de Claude lo pueda leer y
    corregir su consulta en el siguiente intento (esto es clave en un loop
    de tool use: los errores también son "resultado" para el modelo).
    """
    try:
        sql_validado = validar_sql(query)
    except SQLNoPermitidoError as e:
        return {"ok": False, "error": str(e), "filas": None}

    sql_final = agregar_limite_si_falta(sql_validado)

    try:
        # read_only=True es la segunda capa de defensa: aunque algo se cuele
        # de la validación de texto, DuckDB en sí mismo rechaza escrituras.
        con = duckdb.connect(DB_PATH, read_only=True)
        resultado = con.execute(sql_final)
        columnas = [d[0] for d in resultado.description]
        filas = resultado.fetchall()
        con.close()

        filas_como_dicts = [dict(zip(columnas, fila)) for fila in filas]

        return {
            "ok": True,
            "error": None,
            "sql_ejecutado": sql_final,
            "columnas": columnas,
            "filas": filas_como_dicts,
            "num_filas": len(filas_como_dicts),
        }
    except Exception as e:
        return {"ok": False, "error": f"Error al ejecutar SQL: {e}", "filas": None}


if __name__ == "__main__":
    # --- Auto-pruebas rápidas de los guardarraíles ---
    print("=== Pruebas de guardarraíles ===\n")

    casos = [
        ("SELECT COUNT(*) FROM mayor_contable", "debe pasar"),
        ("select cuenta_contable, sum(monto_dolar_neto) from mayor_contable group by 1", "debe pasar"),
        ("DROP TABLE mayor_contable", "debe bloquearse"),
        ("SELECT * FROM mayor_contable; DROP TABLE mayor_contable", "debe bloquearse"),
        ("DELETE FROM presupuesto WHERE 1=1", "debe bloquearse"),
        ("UPDATE mayor_contable SET MONTO_DOLAR_NETO = 0", "debe bloquearse"),
        ("INSERT INTO catalogo_cuentas VALUES (1)", "debe bloquearse"),
        ("", "debe bloquearse (vacío)"),
    ]

    for sql, esperado in casos:
        resultado = ejecutar_sql_seguro(sql)
        estado = "✅ PASÓ" if resultado["ok"] else f"🛑 BLOQUEADO ({resultado['error']})"
        print(f"[{esperado:25s}] {sql[:60]!r:65s} -> {estado}")

    print("\n=== Prueba real con límite automático ===")
    r = ejecutar_sql_seguro("SELECT CUENTA_CONTABLE, MONTO_DOLAR_NETO FROM mayor_contable")
    print(f"ok={r['ok']}, num_filas={r['num_filas']} (debe ser <= {LIMIT_MAXIMO_FILAS})")
    print("SQL final ejecutado:", r["sql_ejecutado"])
