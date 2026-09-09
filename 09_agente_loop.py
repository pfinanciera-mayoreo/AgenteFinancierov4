"""
Día 2 - Loop de tool use con la API de Claude.

¿Qué es un "loop de tool use"? Claude no ejecuta SQL directamente — nosotros le
damos la HERRAMIENTA (la función ejecutar_sql_seguro del paso anterior) descrita
como si fuera un menú de opciones, y Claude decide CUÁNDO usarla y CON QUÉ
parámetros. El flujo real es una conversación de varias vueltas:

  1. Nosotros: "¿por qué subió el gasto de mantenimiento en agosto?" + la
     definición de la herramienta "ejecutar_sql".
  2. Claude responde: "quiero usar ejecutar_sql con este query: SELECT..."
     (esto se llama un bloque tool_use, NO es la respuesta final).
  3. Nosotros ejecutamos ESE SQL de verdad (con nuestros guardarraíles) y le
     devolvemos el resultado a Claude como tool_result.
  4. Claude puede pedir OTRA consulta si necesita más información (ej. primero
     agregado, luego detalle transaccional) -> se repite el paso 2-3.
  5. Cuando Claude ya tiene lo que necesita, responde con texto normal
     (sin tool_use) -> ahí termina el loop.

Por eso esto es un "while" y no una sola llamada a la API.
"""
import json
import anthropic
from importlib import import_module

sql_tool = import_module("07_sql_tool")  # reutilizamos ejecutar_sql_seguro
from importlib import import_module as _im
SYSTEM_PROMPT_AGENTE_FINANCIERO_V2 = _im("08_system_prompt").SYSTEM_PROMPT_AGENTE_FINANCIERO_V2

MODELO = "claude-haiku-4-5-20251001"  # cambiado de Sonnet a Haiku: más rápido y económico para text-to-SQL
MAX_VUELTAS_DE_HERRAMIENTA = 8  # subido de 5 a 8: preguntas que necesitan desambiguar
# una categoría (ej. "Personal" tiene 4 variantes) Y comparar 2+ meses pueden
# necesitar más de 5 idas-y-vueltas antes de tener todo lo necesario.
MAX_TOKENS_RESPUESTA = 4096  # subido de 2000: preguntas con varias partes (variación
# mensual + interanual + causas + gráfico) necesitan más espacio para el análisis
# final en texto, si no se corta antes de terminar de explicar.

# --- Definición de la herramienta que Claude puede usar ---
# Esto NO es código que se ejecuta: es una "ficha técnica" en formato que la
# API de Claude entiende, para que el modelo sepa que existe esta opción,
# qué hace, y qué parámetros necesita.
HERRAMIENTAS = [
    {
        "name": "ejecutar_sql",
        "description": (
            "Ejecuta una consulta SQL de solo lectura (SELECT) contra la base de "
            "datos financiera en DuckDB y devuelve los resultados. Úsala para "
            "responder preguntas sobre presupuesto, gasto real (mayor contable) "
            "y clasificación de cuentas. Solo se permiten sentencias SELECT."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La consulta SQL SELECT a ejecutar.",
                }
            },
            "required": ["query"],
        },
    }
]




def preguntar_al_agente(pregunta_usuario: str, api_key: str, workspace_id: str = None, historial_previo: list = None) -> dict:
    """
    Corre el loop completo: manda la pregunta a Claude, ejecuta las
    herramientas que pida, y devuelve la respuesta final junto con el
    historial de SQL ejecutado (para mostrar transparencia en Streamlit).

    workspace_id: algunas API keys ("vinculadas a identidad") requieren
    indicar en cada solicitud a qué Workspace de la organización pertenece
    la petición, vía el encabezado 'anthropic-workspace-id'. Si tu key es
    de este tipo, la API te lo pide explícitamente en el mensaje de error
    ("anthropic-workspace-id is required..."); si no, puedes dejar este
    parámetro vacío sin problema.

    historial_previo: lista de turnos simples [{"role": "user"/"assistant",
    "content": "texto"}] de la conversación activa, SIN los bloques de
    tool_use/tool_result (esos solo se usan dentro de una misma pregunta,
    no hace falta reenviarlos en cada nueva pregunta — sería carísimo en
    tokens y no aporta nada extra). Con esto, el agente "recuerda" lo que
    ya se preguntó/respondió antes en la misma conversación.
    """
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    client = anthropic.Anthropic(api_key=api_key, default_headers=headers)

    mensajes = list(historial_previo) if historial_previo else []
    mensajes.append({"role": "user", "content": pregunta_usuario})
    sql_ejecutados = []  # para mostrarle al usuario qué SQL corrió el agente

    for _ in range(MAX_VUELTAS_DE_HERRAMIENTA):
        respuesta = client.messages.create(
            model=MODELO,
            max_tokens=MAX_TOKENS_RESPUESTA,
            system=SYSTEM_PROMPT_AGENTE_FINANCIERO_V2,
            tools=HERRAMIENTAS,
            messages=mensajes,
        )

        # Si Claude no pidió usar ninguna herramienta, ya tenemos la respuesta final.
        if respuesta.stop_reason != "tool_use":
            texto_final = "".join(
                bloque.text for bloque in respuesta.content if bloque.type == "text"
            )
            return {"respuesta": texto_final, "sql_ejecutados": sql_ejecutados}

        # Guardamos la respuesta de Claude (incluye el/los tool_use) en el historial.
        mensajes.append({"role": "assistant", "content": respuesta.content})

        # Claude puede pedir varias herramientas en una misma vuelta; las
        # recorremos todas y por cada una devolvemos su resultado.
        bloques_resultado = []
        for bloque in respuesta.content:
            if bloque.type != "tool_use":
                continue

            query = bloque.input["query"]
            resultado = sql_tool.ejecutar_sql_seguro(query)
            sql_ejecutados.append({"query": query, "resultado": resultado})

            bloques_resultado.append({
                "type": "tool_result",
                "tool_use_id": bloque.id,
                "content": json.dumps(resultado, ensure_ascii=False, default=str),
            })

        # Le devolvemos a Claude el/los resultado(s) para que siga razonando.
        mensajes.append({"role": "user", "content": bloques_resultado})

    return {
        "respuesta": "El agente hizo demasiadas consultas seguidas sin llegar a una respuesta final.",
        "sql_ejecutados": sql_ejecutados,
    }


if __name__ == "__main__":
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Falta la variable de entorno ANTHROPIC_API_KEY. Configúrala así:")
        print("  export ANTHROPIC_API_KEY='tu-api-key-aqui'   (Mac/Linux)")
        print("  set ANTHROPIC_API_KEY=tu-api-key-aqui        (Windows cmd)")
        raise SystemExit(1)

    # Opcional: solo hace falta si tu API key es "vinculada a identidad"
    # (la API lo pide explícitamente con un error si es tu caso).
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")

    pregunta = "¿Cuál fue el gasto total en Publicidad y Propaganda de Febeca en 2026?"
    resultado = preguntar_al_agente(pregunta, api_key, workspace_id)

    print("PREGUNTA:", pregunta)
    print("\nSQL EJECUTADO(S):")
    for item in resultado["sql_ejecutados"]:
        print(" ", item["query"])
    print("\nRESPUESTA DEL AGENTE:\n", resultado["respuesta"])
