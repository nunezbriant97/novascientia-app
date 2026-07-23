"""
Servidor Flask de NovaScientia AI.

Por ahora tiene un solo endpoint real: buscar artículos en las fuentes
que elijas, guardarlos en SQLite (con deduplicación por DOI), y
devolverlos. Los próximos endpoints (proyectos, hipótesis, motor de IA)
se van a ir agregando de a uno, sobre esta misma base.
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from database import get_connection, guardar_hipotesis, init_db
from adapters import crossref, europepmc, openalex, plos, semantic_scholar
import groq_client

load_dotenv()  # lee el archivo .env y carga las claves como variables de entorno

app = Flask(__name__)


@app.after_request
def _agregar_headers_cors(response):
    """
    Permite que el frontend (el archivo HTML, abierto directo en el
    navegador o servido desde otro origen) pueda llamar a esta API sin
    que el navegador lo bloquee por CORS.
    """
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/<path:ruta>", methods=["OPTIONS"])
def _preflight_cors(ruta):
    # El navegador manda esto antes de un POST con JSON, para preguntar
    # si tiene permiso -- le contestamos que sí, sin hacer nada más.
    return "", 200

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


@app.route("/")
def index():
    """
    Sirve el frontend (novascientia-app.html) directamente desde Flask.

    Esto es clave: si abrís el HTML con doble clic (protocolo file://),
    Chrome bloquea los pedidos hacia la API por seguridad. Sirviéndolo
    desde acá, todo corre bajo el mismo origen (http://localhost:5000)
    y ese problema desaparece.

    Requiere que "novascientia-app.html" esté en la misma carpeta que
    este app.py.
    """
    carpeta = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(carpeta, "novascientia-app.html")


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


def _armar_contexto(conn, tema: str | None, articulo_ids: list[int]) -> str:
    """
    Arma el texto de "contexto" que se le manda al Núcleo IA para que
    pueda evaluar novedad de verdad en base a evidencia real, en vez
    de inventar. Junta el tema (si lo mandaron) con los resúmenes de
    los artículos elegidos como evidencia.
    """
    partes = []
    if tema:
        partes.append(f"Tema propuesto para la hipótesis: {tema}")

    if articulo_ids:
        placeholders = ",".join("?" * len(articulo_ids))
        filas = conn.execute(
            f"""
            SELECT id, doi, titulo, resumen, resumen_ia, anio_publicacion
            FROM articulos WHERE id IN ({placeholders})
            """,
            articulo_ids,
        ).fetchall()

        partes.append("Evidencia recuperada (artículos ya indexados):")
        for fila in filas:
            resumen = fila["resumen_ia"] or fila["resumen"] or "(sin resumen disponible)"
            partes.append(
                f"- [id={fila['id']}, doi={fila['doi']}, año={fila['anio_publicacion']}] "
                f"{fila['titulo']}: {resumen}"
            )

    return "\n\n".join(partes)


@app.route("/api/hipotesis/generar", methods=["POST"])
def generar_hipotesis_endpoint():
    """
    Genera una hipótesis con el Núcleo IA (DeepSeek), aplicando los 5
    filtros del protocolo de innovación, y la guarda en la base
    (generada o descartada -- se guarda igual, para tener el historial).

    Espera un JSON en el body:
        {
            "tema": "biofertilizantes en suelos ácidos",   (opcional)
            "articulo_ids": [12, 34, 57],                  (opcional, recomendado)
            "proyecto_id": 3                               (opcional)
        }

    Al menos "tema" o "articulo_ids" tiene que venir -- sin nada de
    evidencia ni tema, el Núcleo IA no tiene sobre qué evaluar novedad.
    """
    datos = request.get_json(silent=True) or {}
    tema = datos.get("tema")
    articulo_ids = datos.get("articulo_ids") or []
    proyecto_id = datos.get("proyecto_id")

    if not tema and not articulo_ids:
        return jsonify({
            "error": "Mandá al menos 'tema' o 'articulo_ids' para tener sobre qué generar la hipótesis"
        }), 400

    conn = get_connection()
    contexto = _armar_contexto(conn, tema, articulo_ids)

    try:
        resultado = groq_client.generar_hipotesis(contexto)
    except RuntimeError as error:
        # Falta GROQ_API_KEY en el .env
        conn.close()
        return jsonify({"error": str(error)}), 500
    except (KeyError, ValueError) as error:
        # El modelo devolvió algo que no se pudo interpretar como el JSON esperado
        conn.close()
        return jsonify({"error": f"Respuesta inesperada del Núcleo IA: {error}"}), 502

    hipotesis_id = guardar_hipotesis(conn, resultado, proyecto_id, articulo_ids)
    conn.close()

    respuesta = {"id": hipotesis_id, **resultado}
    codigo = 201 if resultado.get("decision_final") == "generada" else 200
    return jsonify(respuesta), codigo


if __name__ == "__main__":
    init_db()
    puerto = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=puerto)
