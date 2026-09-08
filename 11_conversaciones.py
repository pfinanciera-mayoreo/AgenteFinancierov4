"""
Proyecto v2 - Guardar y cargar conversaciones, por usuario.

Se guarda en un archivo DuckDB SEPARADO (data/conversaciones.duckdb), para
que recargar los datos financieros (06_cargar_todo.py) nunca borre el
historial de conversaciones guardadas.

Cada persona pone su nombre al entrar (no hay login real todavía) y solo ve
sus propias conversaciones guardadas — filtramos por ese nombre.
"""
import os
import json
import uuid
from datetime import datetime

import duckdb

DB_PATH = "data/conversaciones.duckdb"


def _conectar():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS conversaciones (
            id VARCHAR PRIMARY KEY,
            usuario VARCHAR,
            titulo VARCHAR,
            fecha TIMESTAMP,
            filtros_json VARCHAR,
            mensajes_json VARCHAR
        )
    """)
    return con


def guardar_conversacion(usuario: str, titulo: str, filtros: dict, mensajes: list) -> str:
    con = _conectar()
    id_conv = str(uuid.uuid4())
    con.execute(
        "INSERT INTO conversaciones VALUES (?, ?, ?, ?, ?, ?)",
        [id_conv, usuario, titulo, datetime.now(),
         json.dumps(filtros, ensure_ascii=False),
         json.dumps(mensajes, ensure_ascii=False, default=str)],
    )
    con.close()
    return id_conv


def listar_conversaciones(usuario: str) -> list:
    con = _conectar()
    filas = con.execute(
        "SELECT id, titulo, fecha FROM conversaciones WHERE usuario = ? ORDER BY fecha DESC",
        [usuario],
    ).fetchall()
    con.close()
    return [{"id": f[0], "titulo": f[1], "fecha": f[2]} for f in filas]


def cargar_conversacion(id_conv: str) -> dict:
    con = _conectar()
    fila = con.execute(
        "SELECT titulo, filtros_json, mensajes_json FROM conversaciones WHERE id = ?",
        [id_conv],
    ).fetchone()
    con.close()
    if not fila:
        return None
    return {
        "titulo": fila[0],
        "filtros": json.loads(fila[1]),
        "mensajes": json.loads(fila[2]),
    }


def eliminar_conversacion(id_conv: str) -> None:
    con = _conectar()
    con.execute("DELETE FROM conversaciones WHERE id = ?", [id_conv])
    con.close()
