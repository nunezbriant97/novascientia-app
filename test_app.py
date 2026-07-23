"""
Prueba app.py SIN llamar a las APIs externas reales.

En vez de golpear internet, "engañamos" a los adapters para que devuelvan
datos de mentira (esto se llama "monkeypatching"), y así probamos que
la lógica del endpoint (guardar en la base, deduplicar, armar la
respuesta JSON) funciona bien.
"""

import os

os.environ["DB_PATH"] = "test_app.db"

import app as app_module
from database import init_db, DB_PATH


def _articulo_falso(fuente: str, doi: str, titulo: str) -> dict:
    """Arma un artículo normalizado de mentira, para no depender de internet."""
    return {
        "doi": doi,
        "identificador_externo": None,
        "titulo": titulo,
        "resumen": "Resumen de prueba",
        "fuente": fuente,
        "revista": "Revista de Prueba",
        "anio_publicacion": 2024,
        "fecha_publicacion": "2024-01-01",
        "tiene_texto_completo": True,
        "licencia": "cc-by",
        "url_fuente": "https://example.org/articulo",
        "citas_count": 3,
        "autores": ["Autor de Prueba"],
        "metadata_raw": "{}",
    }


def test_buscar_endpoint_sin_fuente_valida():
    init_db()
    cliente = app_module.app.test_client()

    respuesta = cliente.get("/api/articulos/buscar?q=suelo&fuente=inventada")
    assert respuesta.status_code == 400
    assert "no reconocida" in respuesta.get_json()["error"]

    print("\n✅ Rechaza correctamente una fuente inexistente")


def test_buscar_endpoint_sin_query():
    cliente = app_module.app.test_client()

    respuesta = cliente.get("/api/articulos/buscar")
    assert respuesta.status_code == 400

    print("✅ Rechaza correctamente una búsqueda sin parámetro 'q'")


def test_buscar_guarda_y_deduplica(monkeypatch):
    """
    Simulamos que OpenAlex y Semantic Scholar devuelven, cada uno, un
    artículo con EL MISMO DOI (como pasaría en la vida real si el mismo
    paper está indexado en las dos fuentes). El resultado guardado en
    la base debe ser UN SOLO artículo, no dos.
    """
    doi_compartido = "https://doi.org/10.5555/mismo-articulo"

    def openalex_fake(consulta, limite=10):
        return [_articulo_falso("openalex", doi_compartido, "Título desde OpenAlex")]

    def semantic_scholar_fake(consulta, limite=10):
        return [_articulo_falso("semantic_scholar", doi_compartido, "Título desde Semantic Scholar")]

    # Reemplazamos temporalmente las funciones reales por las falsas
    monkeypatch.setattr(app_module.openalex, "buscar", openalex_fake)
    monkeypatch.setattr(app_module.semantic_scholar, "buscar", semantic_scholar_fake)
    # Las demás fuentes las dejamos devolver una lista vacía para no
    # necesitar mockear todas
    monkeypatch.setattr(app_module.crossref, "buscar", lambda c, l=10: [])
    monkeypatch.setattr(app_module.europepmc, "buscar", lambda c, l=10: [])
    monkeypatch.setattr(app_module.plos, "buscar", lambda c, l=10: [])

    cliente = app_module.app.test_client()
    respuesta = cliente.get("/api/articulos/buscar?q=prueba&fuente=todas")

    assert respuesta.status_code == 200
    datos = respuesta.get_json()

    # Deberíamos tener 2 resultados en la respuesta (uno por cada
    # fuente que lo encontró), pero...
    assert datos["total"] == 2

    # ...al mirar la base de datos, debe haber SOLO 1 fila con ese DOI
    # (la deduplicación funcionó)
    conn = app_module.get_connection()
    filas = conn.execute(
        "SELECT COUNT(*) as cantidad FROM articulos WHERE doi = ?",
        (doi_compartido,),
    ).fetchone()
    conn.close()

    assert filas["cantidad"] == 1
    print(f"✅ Dos fuentes devolvieron el mismo DOI, pero se guardó 1 sola vez en la base")


if __name__ == "__main__":
    import types

    test_buscar_endpoint_sin_fuente_valida()
    test_buscar_endpoint_sin_query()

    # monkeypatch manual, sin pytest, para poder correr con "python3" directo
    class MonkeypatchSimple:
        def setattr(self, obj, nombre, valor):
            setattr(obj, nombre, valor)

    test_buscar_guarda_y_deduplica(MonkeypatchSimple())

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    print("\n✅ Todo funciona correctamente (base de datos de prueba eliminada)")
