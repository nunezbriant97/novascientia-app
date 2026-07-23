"""
Adapter de PLOS (Public Library of Science).

PLOS es 100% open access, así que acá SIEMPRE vas a tener texto completo
disponible -- a diferencia de Crossref, donde muchas veces no lo hay.

Su API es de tipo "Solr" (un motor de búsqueda), un poco distinta a las
anteriores en la forma de pedir los campos, pero el patrón de traducción
es el mismo de siempre.

Documentación: https://api.plos.org/solr/search-fields/

Estructura de siempre:
1. mapear_a_articulo()  -> traduce UN resultado a nuestro esquema
2. buscar()             -> llama a la API y devuelve la lista normalizada
"""

import requests

from adapters.base import articulo_vacio, guardar_metadata_raw

BASE_URL = "https://api.plos.org/search"

# Le decimos a PLOS exactamente qué campos queremos en la respuesta
# (si no se especifica, la API devuelve de más y es más lenta)
CAMPOS = "id,title_display,abstract,author_display,journal,publication_date,counter_total_all"


def mapear_a_articulo(item: dict) -> dict:
    """
    Traduce un resultado crudo de PLOS a nuestro esquema normalizado.
    """
    articulo = articulo_vacio()

    articulo["fuente"] = "plos"

    # En PLOS, el campo "id" ES el DOI directamente (sin el prefijo https://doi.org/)
    doi_crudo = item.get("id")
    articulo["doi"] = f"https://doi.org/{doi_crudo}" if doi_crudo else None
    articulo["identificador_externo"] = doi_crudo

    articulo["titulo"] = item.get("title_display")

    # El abstract viene como una LISTA de strings (a veces con varias
    # secciones), las unimos en un solo texto
    abstract_lista = item.get("abstract", [])
    articulo["resumen"] = " ".join(abstract_lista) if abstract_lista else None

    articulo["revista"] = item.get("journal")

    # publication_date viene como fecha completa con hora, ej: "2023-05-10T00:00:00Z"
    fecha_completa = item.get("publication_date")
    if fecha_completa:
        articulo["fecha_publicacion"] = fecha_completa[:10]  # nos quedamos solo con la parte de fecha
        articulo["anio_publicacion"] = int(fecha_completa[:4])

    # PLOS es siempre de acceso abierto -- por eso esto va fijo en True,
    # a diferencia de los demás adapters donde depende de cada artículo
    articulo["tiene_texto_completo"] = True
    articulo["licencia"] = "cc-by"  # PLOS publica todo bajo CC-BY

    if doi_crudo:
        articulo["url_fuente"] = f"https://journals.plos.org/plosone/article?id={doi_crudo}"

    # counter_total_all es un proxy de "vistas/uso", no citas reales --
    # PLOS no da un conteo de citas propio en esta API, así que lo dejamos
    # en 0 en vez de usar un número que no significa lo mismo que en otras fuentes
    articulo["citas_count"] = 0

    articulo["autores"] = item.get("author_display", [])

    guardar_metadata_raw(articulo, item)

    return articulo


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """
    Busca artículos en PLOS y devuelve la lista normalizada.

    Ejemplo de uso:
        resultados = buscar("agricultura regenerativa suelo", limite=5)
    """
    parametros = {
        "q": consulta,
        "fl": CAMPOS,
        "rows": limite,
        "wt": "json",
    }

    respuesta = requests.get(BASE_URL, params=parametros, timeout=15)
    respuesta.raise_for_status()

    datos = respuesta.json()
    items_crudos = datos.get("response", {}).get("docs", [])

    return [mapear_a_articulo(item) for item in items_crudos]
