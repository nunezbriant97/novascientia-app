"""
Prueba que init_db() crea todas las tablas esperadas, y que las
restricciones (CHECK, UNIQUE) funcionan como se diseñaron.

Usa un archivo de base de datos temporal (no toca tu novascientia.db real).
"""

import os

# Antes de importar database.py, le decimos que use un archivo de prueba
os.environ["DB_PATH"] = "test_novascientia.db"

import sqlite3
from database import init_db, get_connection, DB_PATH

TABLAS_ESPERADAS = {
    "archivos_temporales",
    "articulos",
    "autores",
    "articulo_autor",
    "proyectos",
    "proyecto_hito",
    "proyecto_articulo",
    "proyecto_actividad_ia",
    "hipotesis",
    "hipotesis_articulo",
}


def test_todas_las_tablas_se_crean():
    init_db()
    conn = get_connection()

    filas = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    nombres_tabla = {fila["name"] for fila in filas}

    faltantes = TABLAS_ESPERADAS - nombres_tabla
    assert not faltantes, f"Faltan tablas: {faltantes}"

    conn.close()
    print(f"\n✅ Se crearon correctamente las {len(TABLAS_ESPERADAS)} tablas esperadas")


def test_dedup_doi_funciona():
    """
    Verifica que el índice único de DOI rechaza artículos duplicados,
    tal como diseñamos para la deduplicación.
    """
    conn = get_connection()

    conn.execute(
        "INSERT INTO articulos (doi, titulo, fuente, url_fuente) VALUES (?, ?, ?, ?)",
        ("https://doi.org/10.1/test", "Artículo de prueba", "openalex", "https://example.org"),
    )
    conn.commit()

    try:
        conn.execute(
            "INSERT INTO articulos (doi, titulo, fuente, url_fuente) VALUES (?, ?, ?, ?)",
            ("https://doi.org/10.1/test", "Mismo articulo de otra fuente", "crossref", "https://example.org/2"),
        )
        conn.commit()
        assert False, "Debería haber rechazado el DOI duplicado"
    except sqlite3.IntegrityError:
        print("✅ El índice único de DOI rechaza correctamente los duplicados")

    conn.close()


def test_check_de_fuente_invalida():
    """
    Verifica que no se puede insertar un artículo con una fuente
    que no está en la lista permitida (protege contra errores de tipeo).
    """
    conn = get_connection()

    try:
        conn.execute(
            "INSERT INTO articulos (titulo, fuente, url_fuente) VALUES (?, ?, ?)",
            ("Artículo con fuente inválida", "fuente_que_no_existe", "https://example.org"),
        )
        conn.commit()
        assert False, "Debería haber rechazado la fuente inválida"
    except sqlite3.IntegrityError:
        print("✅ El CHECK de 'fuente' rechaza correctamente valores no permitidos")

    conn.close()


if __name__ == "__main__":
    test_todas_las_tablas_se_crean()
    test_dedup_doi_funciona()
    test_check_de_fuente_invalida()

    # Limpiamos el archivo de prueba para no dejar basura
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    print("\n✅ Todo funciona correctamente (base de datos de prueba eliminada)")
