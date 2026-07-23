"""
Conexión a la base de datos SQLite y creación de todas las tablas.

Este archivo junta las tablas que fuimos diseñando en el chat:
- archivos_temporales   (PDFs de Mega.nz + imágenes de Flux, expiran a los 30 días)
- articulos             (el esquema normalizado que llenan los adapters)
- autores + articulo_autor
- proyectos + proyecto_hito + proyecto_articulo + proyecto_actividad_ia
- hipotesis + hipotesis_articulo

Uso típico en el resto de la app:

    from database import get_connection

    conn = get_connection()
    conn.execute("INSERT INTO articulos (...) VALUES (...)")
    conn.commit()
"""

import json
import os
import sqlite3

# El nombre/ubicación del archivo de la base de datos. Se puede cambiar
# desde el .env si en algún momento se quiere mover a otra carpeta.
DB_PATH = os.environ.get("DB_PATH", "novascientia.db")


def get_connection() -> sqlite3.Connection:
    """
    Abre una conexión a la base de datos.

    row_factory = sqlite3.Row hace que cada fila se pueda leer como si
    fuera un diccionario (fila["titulo"]) en vez de por posición (fila[2]),
    que es mucho más fácil de leer en el resto del código.

    timeout=10: si otra conexión tiene la base ocupada un instante (algo
    normal en SQLite cuando hay varios requests casi al mismo tiempo),
    espera hasta 10 segundos antes de tirar "database is locked", en vez
    de fallar al toque.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # Sin esto, SQLite ignora las FOREIGN KEY por defecto (por compatibilidad
    # histórica). Lo activamos para que se respeten de verdad.
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL permite que una lectura y una escritura convivan sin bloquearse
    # mutuamente -- reduce mucho los "database is locked" cuando el chat
    # (evidencia.py) y una búsqueda de artículos golpean la base casi
    # al mismo tiempo.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def guardar_articulo(conn: sqlite3.Connection, articulo: dict) -> int:
    """
    Guarda un artículo normalizado en la base de datos.

    Si ya existe un artículo con el mismo DOI (venido de otra fuente),
    actualiza algunos campos (citas, tiene_texto_completo) en vez de
    crear un duplicado -- esta es la deduplicación que diseñamos.

    Vive acá (y no en app.py) porque tanto /api/articulos/buscar como
    evidencia.py (usado por el chat) necesitan guardar artículos, y no
    queremos duplicar la lógica ni tener imports circulares.

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


# Todas las sentencias CREATE TABLE que diseñamos, en el orden correcto
# (las tablas que otras referencian con FOREIGN KEY van primero).
TABLAS_SQL = [
    """
    CREATE TABLE IF NOT EXISTS archivos_temporales (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo             TEXT NOT NULL CHECK(tipo IN ('pdf', 'imagen')),
        entidad_tipo     TEXT NOT NULL CHECK(entidad_tipo IN ('articulo', 'proyecto')),
        entidad_id       INTEGER NOT NULL,
        mega_node_id     TEXT NOT NULL,
        mega_link        TEXT,
        nombre_archivo   TEXT NOT NULL,
        tamano_bytes     INTEGER,
        metadata         TEXT,
        fecha_creacion   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_expiracion DATETIME NOT NULL,
        eliminado        BOOLEAN NOT NULL DEFAULT 0,
        fecha_eliminado  DATETIME
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_archivos_expiracion
        ON archivos_temporales(fecha_expiracion) WHERE eliminado = 0
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_archivos_entidad
        ON archivos_temporales(entidad_tipo, entidad_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS articulos (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        doi                    TEXT,
        identificador_externo  TEXT,
        titulo                 TEXT NOT NULL,
        resumen                TEXT,
        fuente                 TEXT NOT NULL CHECK(fuente IN (
                                    'openalex','semantic_scholar','crossref','pubmed','europepmc',
                                    'orcid','plos','elife','bmc','frontiers','mdpi',
                                    'f1000research','peerj','nature','science','cell','lancet'
                                )),
        revista                TEXT,
        anio_publicacion       INTEGER,
        fecha_publicacion      DATE,
        tiene_texto_completo   BOOLEAN NOT NULL DEFAULT 0,
        licencia               TEXT,
        url_fuente             TEXT NOT NULL,
        citas_count            INTEGER DEFAULT 0,
        metadata_raw           TEXT,
        archivo_temporal_id    INTEGER REFERENCES archivos_temporales(id),
        resumen_ia             TEXT,
        resumen_ia_generado_en DATETIME,
        fecha_indexado         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizado      DATETIME
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_articulos_doi
        ON articulos(doi) WHERE doi IS NOT NULL
    """,
    "CREATE INDEX IF NOT EXISTS idx_articulos_fuente ON articulos(fuente)",
    "CREATE INDEX IF NOT EXISTS idx_articulos_anio ON articulos(anio_publicacion)",
    """
    CREATE TABLE IF NOT EXISTS autores (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_completo     TEXT NOT NULL,
        orcid               TEXT,
        semantic_scholar_id TEXT,
        institucion         TEXT,
        pais                TEXT,
        area_especialidad   TEXT,
        h_index             INTEGER,
        citas_totales       INTEGER,
        publicaciones_count INTEGER,
        metadata_raw        TEXT,
        fecha_indexado      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizado   DATETIME
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_autores_orcid
        ON autores(orcid) WHERE orcid IS NOT NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS articulo_autor (
        articulo_id INTEGER NOT NULL REFERENCES articulos(id),
        autor_id    INTEGER NOT NULL REFERENCES autores(id),
        orden       INTEGER,
        PRIMARY KEY (articulo_id, autor_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_articulo_autor_autor ON articulo_autor(autor_id)",
    """
    CREATE TABLE IF NOT EXISTS proyectos (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo            TEXT NOT NULL,
        descripcion       TEXT,
        categoria         TEXT,
        estado            TEXT NOT NULL DEFAULT 'idea_inicial' CHECK(estado IN (
                              'idea_inicial','revision_cientifica','investigacion_en_curso',
                              'finalizado','archivado'
                          )),
        progreso_pct      INTEGER NOT NULL DEFAULT 0 CHECK(progreso_pct BETWEEN 0 AND 100),
        patentes_count    INTEGER DEFAULT 0,
        fecha_creacion    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizado DATETIME
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS proyecto_hito (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id      INTEGER NOT NULL REFERENCES proyectos(id),
        nombre           TEXT NOT NULL,
        completado       BOOLEAN NOT NULL DEFAULT 0,
        orden            INTEGER NOT NULL,
        fecha_completado DATETIME
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hito_proyecto ON proyecto_hito(proyecto_id)",
    """
    CREATE TABLE IF NOT EXISTS proyecto_articulo (
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id),
        articulo_id INTEGER NOT NULL REFERENCES articulos(id),
        PRIMARY KEY (proyecto_id, articulo_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS proyecto_actividad_ia (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id INTEGER NOT NULL REFERENCES proyectos(id),
        descripcion TEXT NOT NULL,
        fecha       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_actividad_proyecto ON proyecto_actividad_ia(proyecto_id)",
    """
    CREATE TABLE IF NOT EXISTS hipotesis (
        id                             INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id                    INTEGER REFERENCES proyectos(id),
        decision_final                 TEXT NOT NULL CHECK(decision_final IN ('generada','descartada')),
        motivo_descarte                TEXT,

        nivel_novedad                  TEXT CHECK(nivel_novedad IN ('alta','media','baja')),
        existe_idea_igual              BOOLEAN,
        existe_combinacion_equivalente BOOLEAN,
        existe_tecnologia_comercial    BOOLEAN,
        existe_patente_relacionada     BOOLEAN,

        descubrimientos_combinados     TEXT,
        es_combinacion_trivial         BOOLEAN,
        nueva_funcion                  TEXT,

        categorias_impacto             TEXT,
        area_agricola                  TEXT CHECK(area_agricola IN ('cultivos','suelos','ganaderia','tecnologia')),
        subtema_agricola               TEXT,

        titulo_cientifico               TEXT,
        idea_central                    TEXT,
        diferencia_estado_actual        TEXT,
        patentes_similares              TEXT,
        riesgos                         TEXT,
        experimentos_sugeridos          TEXT,

        fecha_creacion                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizado               DATETIME
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hipotesis_proyecto ON hipotesis(proyecto_id)",
    "CREATE INDEX IF NOT EXISTS idx_hipotesis_decision ON hipotesis(decision_final)",
    "CREATE INDEX IF NOT EXISTS idx_hipotesis_novedad ON hipotesis(nivel_novedad)",
    "CREATE INDEX IF NOT EXISTS idx_hipotesis_area ON hipotesis(area_agricola)",
    """
    CREATE TABLE IF NOT EXISTS hipotesis_articulo (
        hipotesis_id INTEGER NOT NULL REFERENCES hipotesis(id),
        articulo_id  INTEGER NOT NULL REFERENCES articulos(id),
        PRIMARY KEY (hipotesis_id, articulo_id)
    )
    """,
]


def guardar_hipotesis(
    conn: sqlite3.Connection,
    resultado_ia: dict,
    proyecto_id: int | None = None,
    articulo_ids: list[int] | None = None,
) -> int:
    """
    Guarda en la tabla `hipotesis` el resultado que devuelve
    groq_client.generar_hipotesis() -- se guarda SIEMPRE, tanto si fue
    "generada" como "descartada" (así queda el historial completo de
    lo que el Núcleo IA evaluó, no solo lo que aprobó).

    Si vinieron articulo_ids (los artículos que se usaron de contexto/
    evidencia), se guarda también la relación en hipotesis_articulo.

    Devuelve el id de la hipótesis insertada.
    """
    novedad = resultado_ia.get("novedad") or {}
    combinacion = resultado_ia.get("combinacion") or {}
    impacto = resultado_ia.get("impacto") or {}
    prioridad = resultado_ia.get("prioridad_agricola") or {}
    hipotesis = resultado_ia.get("hipotesis") or {}
    antecedentes = hipotesis.get("antecedentes") or {}

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO hipotesis (
            proyecto_id, decision_final, motivo_descarte,
            nivel_novedad, existe_idea_igual, existe_combinacion_equivalente,
            existe_tecnologia_comercial, existe_patente_relacionada,
            descubrimientos_combinados, es_combinacion_trivial, nueva_funcion,
            categorias_impacto, area_agricola, subtema_agricola,
            titulo_cientifico, idea_central, diferencia_estado_actual,
            patentes_similares, riesgos, experimentos_sugeridos
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            proyecto_id,
            resultado_ia.get("decision_final"),
            resultado_ia.get("motivo_descarte"),
            novedad.get("nivel"),
            novedad.get("existe_idea_igual"),
            novedad.get("existe_combinacion_equivalente"),
            novedad.get("existe_tecnologia_comercial"),
            novedad.get("existe_patente_relacionada"),
            json.dumps(combinacion.get("descubrimientos"), ensure_ascii=False),
            combinacion.get("es_trivial"),
            combinacion.get("nueva_funcion"),
            json.dumps(impacto.get("categorias_cumplidas"), ensure_ascii=False),
            prioridad.get("area"),
            prioridad.get("subtema"),
            hipotesis.get("titulo_cientifico"),
            hipotesis.get("idea_central"),
            hipotesis.get("diferencia_estado_actual"),
            json.dumps(antecedentes.get("patentes_similares"), ensure_ascii=False),
            json.dumps(hipotesis.get("riesgos"), ensure_ascii=False),
            json.dumps(hipotesis.get("experimentos_sugeridos"), ensure_ascii=False),
        ),
    )
    hipotesis_id = cursor.lastrowid

    if articulo_ids:
        cursor.executemany(
            "INSERT OR IGNORE INTO hipotesis_articulo (hipotesis_id, articulo_id) VALUES (?, ?)",
            [(hipotesis_id, articulo_id) for articulo_id in articulo_ids],
        )

    conn.commit()
    return hipotesis_id


def init_db() -> None:
    """
    Crea todas las tablas si todavía no existen.
    Usar "IF NOT EXISTS" en cada CREATE hace que se pueda llamar esta
    función cada vez que arranca el servidor, sin riesgo de romper nada
    si las tablas ya estaban creadas de antes.
    """
    conn = get_connection()
    try:
        for sentencia in TABLAS_SQL:
            conn.execute(sentencia)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    # Ejecutar este archivo directo ("python3 database.py") crea la base
    # de datos y todas las tablas, si todavía no existen.
    init_db()
    print(f"Base de datos lista en: {DB_PATH}")
