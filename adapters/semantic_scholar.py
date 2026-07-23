"""
Adapter de Semantic Scholar.

A diferencia de OpenAlex, Semantic Scholar te da el abstract como texto
plano directo, sin tener que reconstruirlo. Es más simple por eso.

Documentación: https://api.semanticscholar.org/api-docs/

Misma estructura que openalex.py:
1. mapear_a_articulo()  -> traduce UN resultado a nuestro esquema
2. buscar()             -> llama a la API y devuelve la lista normalizada
"""

import requests

from adapters.base import articulo_vacio, guardar_metadata_raw

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

# Le pedimos a la API justo los campos que necesitamos (así la respuesta
# es más liviana y rápida). Si querés más datos en el futuro, se agregan acá.
CAMPOS = "title,abstract,year,publicationDate,venue,citationCount,openAccessPdf,externalIds,authors"


def mapear_a_articulo(item: dict) -> dict:
    """
    Traduce un resultado crudo de Semantic Scholar a nuestro esquema normalizado.
    """
    articulo = articulo_vacio()

    articulo["fuente"] = "semantic_scholar"
    articulo["titulo"] = item.get("title")
    articulo["resumen"] = item.get("abstract")  # ya viene como texto plano
    articulo["anio_publicacion"] = item.get("year")
    articulo["fecha_publicacion"] = item.get("publicationDate")
    articulo["revista"] = item.get("venue")
    articulo["citas_count"] = item.get("citationCount", 0)

    # El DOI viene adentro de "externalIds", junto con otros IDs (PubMed, arXiv, etc.)
    external_ids = item.get("externalIds") or {}
    doi = external_ids.get("DOI")
    articulo["doi"] = f"https://doi.org/{doi}" if doi else None
    articulo["identificador_externo"] = item.get("paperId")

    # Si Semantic Scholar encontró un PDF de acceso abierto, nos da el link directo
    pdf_info = item.get("openAccessPdf") or {}
    if pdf_info.get("url"):
        articulo["tiene_texto_completo"] = True
        articulo["url_fuente"] = pdf_info["url"]
        articulo["licencia"] = pdf_info.get("license")
    else:
        articulo["tiene_texto_completo"] = False
        # Si no hay PDF abierto, igual guardamos el link a la página del paper
        if articulo["identificador_externo"]:
            articulo["url_fuente"] = f"https://www.semanticscholar.org/paper/{articulo['identificador_externo']}"

    # Los autores vienen en una lista simple de {name: "..."}
    articulo["autores"] = [
        autor.get("name") for autor in item.get("authors", []) if autor.get("name")
    ]

    guardar_metadata_raw(articulo, item)

    return articulo


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """
    Busca artículos en Semantic Scholar y devuelve la lista normalizada.

    Ejemplo de uso:
        resultados = buscar("biofertilizantes cultivos de soja", limite=5)
    """
    parametros = {
        "query": consulta,
        "limit": limite,
        "fields": CAMPOS,
    }

    respuesta = requests.get(BASE_URL, params=parametros, timeout=15)
    respuesta.raise_for_status()

    datos = respuesta.json()
    items_crudos = datos.get("data", [])

    return [mapear_a_articulo(item) for item in items_crudos]
