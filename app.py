"""
Servidor Flask de NovaScientia AI.

Por ahora tiene un solo endpoint real: buscar artículos en las fuentes
que elijas, guardarlos en SQLite (con deduplicación por DOI), y
devolverlos. Los próximos endpoints (proyectos, hipótesis, motor de IA)
se van a ir agregando de a uno, sobre esta misma base.
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from database import get_connection, init_db
from adapters import crossref, europepmc, openalex, plos, semantic_scholar
import sve

load_dotenv()  # lee el archivo .env y carga las claves como variables de entorno

app = Flask(__name__)

# Todas las fuentes de búsqueda de artículos disponibles hasta ahora.
# ORCID no entra acá porque busca autores, no artículos -- va a tener
# su propio endpoint más adelante.
ADAPTERS = {
    "openalex": openalex,
    "semantic_scholar": semantic_scholar,
    "crossref": crossref,
    "europepmc": europepmc,
    "plos": plos,
}


def guardar_articulo(conn, articulo: dict) -> int:
    """
    Guarda un artículo normalizado en la base de datos.

    Si ya existe un artículo con el mismo DOI (venido de otra fuente),
    actualiza algunos campos (citas, tiene_texto_completo) en vez de
    crear un duplicado -- esta es la deduplicación que diseñamos.

    Devuelve el id del artículo en la base (nuevo o existente).
    """
    cursor = conn.cursor()

    articulo_existente = None
    if articulo.get("doi"):
        articulo_existente = cursor.execute(
            "SELECT id FROM articulos WHERE doi = ?", (articulo["doi"],)
        ).fetchone()

    if articulo_existente:
        # Ya lo teníamos (de esta u otra fuente) -- actualizamos algunos
        # campos que pueden haber cambiado, pero NO tocamos resumen_ia
        # (eso lo genera el motor de IA aparte, no queremos perderlo)
        cursor.execute(
            """
            UPDATE articulos
            SET citas_count = ?, tiene_texto_completo = ?, fecha_actualizado = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                articulo.get("citas_count", 0),
                articulo.get("tiene_texto_completo", False),
                articulo_existente["id"],
            ),
        )
        return articulo_existente["id"]

    # No existía -- lo insertamos nuevo
    cursor.execute(
        """
        INSERT INTO articulos (
            doi, identificador_externo, titulo, resumen, fuente, revista,
            anio_publicacion, fecha_publicacion, tiene_texto_completo,
            licencia, url_fuente, citas_count, metadata_raw
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            articulo.get("doi"),
            articulo.get("identificador_externo"),
            articulo.get("titulo"),
            articulo.get("resumen"),
            articulo.get("fuente"),
            articulo.get("revista"),
            articulo.get("anio_publicacion"),
            articulo.get("fecha_publicacion"),
            articulo.get("tiene_texto_completo", False),
            articulo.get("licencia"),
            articulo.get("url_fuente"),
            articulo.get("citas_count", 0),
            articulo.get("metadata_raw"),
        ),
    )
    return cursor.lastrowid


@app.route("/api/articulos/buscar", methods=["GET"])
def buscar_articulos():
    """
    Busca artículos en una o varias fuentes, los guarda en la base
    (evitando duplicados por DOI), y devuelve la lista resultante.

    Parámetros de la URL:
        q       -> la consulta de búsqueda (obligatorio)
        fuente  -> "todas" (default) o una fuente puntual: openalex,
                   semantic_scholar, crossref, europepmc, plos
        limite  -> cuántos resultados pedirle a CADA fuente (default 10)

    Ejemplo:
        GET /api/articulos/buscar?q=biofertilizantes&fuente=todas&limite=5
    """
    consulta = request.args.get("q")
    if not consulta:
        return jsonify({"error": "Falta el parámetro 'q' con la búsqueda"}), 400

    fuente_pedida = request.args.get("fuente", "todas")
    limite = int(request.args.get("limite", 10))

    if fuente_pedida == "todas":
        fuentes_a_consultar = list(ADAPTERS.keys())
    elif fuente_pedida in ADAPTERS:
        fuentes_a_consultar = [fuente_pedida]
    else:
        return jsonify({
            "error": f"Fuente '{fuente_pedida}' no reconocida. "
                     f"Opciones: {list(ADAPTERS.keys())} o 'todas'"
        }), 400

    conn = get_connection()
    resultados = []
    errores = {}

    for nombre_fuente in fuentes_a_consultar:
        try:
            articulos_encontrados = ADAPTERS[nombre_fuente].buscar(consulta, limite)
        except Exception as error:
            # Si una fuente falla (ej: está caída, o sin internet), no
            # queremos que se rompa toda la búsqueda -- guardamos el
            # error y seguimos con las demás fuentes
            errores[nombre_fuente] = str(error)
            continue

        for articulo in articulos_encontrados:
            articulo_id = guardar_articulo(conn, articulo)
            articulo["id"] = articulo_id
            resultados.append(articulo)

    conn.commit()
    conn.close()

    respuesta = {"resultados": resultados, "total": len(resultados)}
    if errores:
        respuesta["errores_por_fuente"] = errores

    return jsonify(respuesta)


@app.route("/api/articulos", methods=["GET"])
def listar_articulos():
    """
    Lista los artículos ya guardados en la base (sin ir a buscar nada
    nuevo a las APIs externas). Sirve para ver lo que ya se indexó.
    """
    conn = get_connection()
    filas = conn.execute(
        "SELECT * FROM articulos ORDER BY fecha_indexado DESC LIMIT 50"
    ).fetchall()
    conn.close()

    return jsonify([dict(fila) for fila in filas])


@app.route("/api/proyectos", methods=["POST"])
def crear_proyecto():
    """
    Crea un proyecto nuevo.

    Body JSON: {"titulo": "..." (requerido), "descripcion": "...", "categoria": "..."}
    """
    datos = request.get_json(silent=True) or {}
    titulo = (datos.get("titulo") or "").strip()
    if not titulo:
        return jsonify({"error": "Falta el campo 'titulo'"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO proyectos (titulo, descripcion, categoria) VALUES (?, ?, ?)",
        (titulo, datos.get("descripcion"), datos.get("categoria")),
    )
    proyecto_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO proyecto_actividad_ia (proyecto_id, descripcion) VALUES (?, ?)",
        (proyecto_id, "Proyecto creado."),
    )
    conn.commit()

    fila = conn.execute("SELECT * FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone()
    conn.close()
    return jsonify(dict(fila)), 201


@app.route("/api/proyectos", methods=["GET"])
def listar_proyectos():
    """Lista todos los proyectos, más recientes primero."""
    conn = get_connection()
    filas = conn.execute("SELECT * FROM proyectos ORDER BY fecha_creacion DESC").fetchall()
    conn.close()
    return jsonify([dict(f) for f in filas])


@app.route("/api/proyectos/<int:proyecto_id>", methods=["GET"])
def obtener_proyecto(proyecto_id):
    """Devuelve un proyecto puntual, junto con su conversación del SVE."""
    conn = get_connection()
    fila = conn.execute("SELECT * FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone()
    if fila is None:
        conn.close()
        return jsonify({"error": "Proyecto no encontrado"}), 404

    proyecto = dict(fila)
    proyecto["mensajes"] = sve.obtener_historial(conn, proyecto_id)
    conn.close()
    return jsonify(proyecto)


@app.route("/api/proyectos/<int:proyecto_id>/mensajes", methods=["POST"])
def enviar_mensaje(proyecto_id):
    """
    Manda un turno de charla al Scientific Visual Engine para un proyecto.

    Body JSON: {"mensaje": "texto del usuario"}

    Si el mensaje es una charla normal, devuelve {"tipo": "texto", "respuesta": "..."}.
    Si el mensaje pide una imagen ("dibújalo", "hazme un render", etc.),
    devuelve {"tipo": "imagen", "titulo": ..., "url": ..., ...}.
    """
    datos = request.get_json(silent=True) or {}
    mensaje = datos.get("mensaje")
    if not mensaje:
        return jsonify({"error": "Falta el campo 'mensaje'"}), 400

    try:
        resultado = sve.responder_mensaje(proyecto_id, mensaje)
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 502

    return jsonify(resultado)


@app.route("/api/proyectos/<int:proyecto_id>/mensajes", methods=["GET"])
def listar_mensajes(proyecto_id):
    """Devuelve toda la conversación guardada de un proyecto (orden cronológico)."""
    conn = get_connection()
    historial = sve.obtener_historial(conn, proyecto_id)
    conn.close()
    return jsonify(historial)


@app.route("/api/proyectos/<int:proyecto_id>/visualizar", methods=["POST"])
def forzar_visualizacion(proyecto_id):
    """
    Genera la imagen del proyecto ya, sin pasar por el chat (ej: para un
    botón "Generar imagen" directo en el frontend).
    """
    conn = get_connection()
    try:
        resultado = sve.generar_visualizacion(conn, proyecto_id)
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 502
    finally:
        conn.close()

    return jsonify(resultado)


if __name__ == "__main__":
    init_db()
    puerto = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=puerto)
