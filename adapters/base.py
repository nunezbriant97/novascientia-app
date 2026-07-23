"""
Esquema normalizado de artículo.

Cada adapter (OpenAlex, Crossref, PubMed, etc.) habla con una API distinta,
con nombres de campos distintos. Este diccionario es el "idioma común" al
que TODOS los adapters tienen que traducir sus resultados, para que el
resto de la app (base de datos, IA, frontend) nunca tenga que preocuparse
de dónde vino cada artículo.

Coincide con las columnas de la tabla `articulos` en SQLite.
"""

import json


def articulo_vacio():
    """
    Devuelve un artículo normalizado con todos los campos en None/vacío.
    Cada adapter parte de esto y va llenando lo que su API le da.
    Así, si una fuente no tiene cierto dato (ej: PubMed no siempre da citas_count),
    el campo queda en None en vez de romper el programa.
    """
    return {
        "doi": None,
        "identificador_externo": None,
        "titulo": None,
        "resumen": None,
        "fuente": None,               # 'openalex', 'crossref', 'pubmed', etc.
        "revista": None,
        "anio_publicacion": None,
        "fecha_publicacion": None,
        "tiene_texto_completo": False,
        "licencia": None,
        "url_fuente": None,
        "citas_count": 0,
        "autores": [],                 # lista de nombres, ej: ["Juan Pérez", "Ana Gómez"]
        "metadata_raw": None,           # el JSON crudo original, como texto
    }


def guardar_metadata_raw(articulo: dict, datos_originales: dict) -> None:
    """
    Guarda el JSON crudo que devolvió la API original, sin transformar.
    Sirve para no perder información y poder re-procesar en el futuro
    sin tener que volver a consultar la API externa.
    """
    articulo["metadata_raw"] = json.dumps(datos_originales, ensure_ascii=False)
