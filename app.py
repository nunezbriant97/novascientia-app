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

from database import get_connection, init_db, guardar_hipotesis
from adapters import crossref, europepmc, openalex, plos, semantic_scholar
import groq_client

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


@app.route("/api/chat", methods=["POST"])
def chat_endpoint():
    """
    Modo conversación general del Núcleo IA.

    Espera un JSON en el body:
        {"mensaje": "¿Qué es un biofertilizante?", "historial": [...]}

    "historial" es opcional -- se usa para que el chat recuerde
    mensajes anteriores de la misma conversación.
    """
    datos = request.get_json(silent=True) or {}
    mensaje = datos.get("mensaje")

    if not mensaje:
        return jsonify({"error": "Falta el campo 'mensaje' en el body"}), 400

    historial = datos.get("historial")

    try:
        respuesta = groq_client.chat(mensaje, historial)
    except RuntimeError as error:
        # Esto salta si falta GROQ_API_KEY en el .env
        return jsonify({"error": str(error)}), 500

    return jsonify({"respuesta": respuesta})


@app.route("/api/hipotesis/generar", methods=["POST"])
def generar_hipotesis_endpoint():
    """
    Genera (o descarta) una hipótesis de investigación aplicando el
    protocolo de 5 filtros del Núcleo IA.

    Body JSON:
        {
          "tema": "biofertilizantes en suelos ácidos" (requerido),
          "proyecto_id": 3 (opcional, para vincular la hipótesis a un proyecto),
          "articulo_ids": [12, 15, 20] (opcional, artículos ya indexados que
                                          se usan como evidencia de contexto)
        }

    Guarda el resultado en la tabla `hipotesis` siempre (generada o
    descartada, para no volver a evaluar la misma idea de cero después),
    y devuelve el resultado.
    """
    datos = request.get_json(silent=True) or {}
    tema = (datos.get("tema") or "").strip()
    if not tema:
        return jsonify({"error": "Falta el campo 'tema'"}), 400

    proyecto_id = datos.get("proyecto_id")
    articulo_ids = datos.get("articulo_ids") or []

    conn = get_connection()

    resumenes_articulos = []
    if articulo_ids:
        placeholders = ",".join("?" * len(articulo_ids))
        filas = conn.execute(
            f"SELECT resumen_ia, resumen FROM articulos WHERE id IN ({placeholders})",
            articulo_ids,
        ).fetchall()
        # Preferimos resumen_ia (ya curado por la IA) y si no existe todavía,
        # usamos el resumen crudo que vino de la fuente.
        resumenes_articulos = [
            fila["resumen_ia"] or fila["resumen"] for fila in filas if fila["resumen_ia"] or fila["resumen"]
        ]

    try:
        resultado = groq_client.generar_hipotesis(tema, resumenes_articulos)
    except RuntimeError as error:
        conn.close()
        return jsonify({"error": str(error)}), 500
    except (ValueError, KeyError) as error:
        # json.loads falló o el modelo devolvió una forma inesperada
        conn.close()
        return jsonify({"error": f"No se pudo interpretar la respuesta de la IA: {error}"}), 502

    hipotesis_id = guardar_hipotesis(conn, resultado, proyecto_id=proyecto_id, articulo_ids=articulo_ids)
    conn.close()

    respuesta = {"id": hipotesis_id, **resultado}
    codigo_http = 201 if resultado.get("decision_final") == "generada" else 200
    return jsonify(respuesta), codigo_http


if __name__ == "__main__":
    init_db()
    puerto = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=puerto)
