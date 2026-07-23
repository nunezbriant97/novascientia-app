"""
Adapter de Europe PMC.

Europe PMC incluye todo el contenido de PubMed, más texto completo de PMC
(PubMed Central) y preprints biomédicos (bioRxiv, medRxiv). Por eso este
UN adapter cubre lo que en tu lista original eran "PubMed" y "Europe PMC"
por separado -- evita duplicar casi el mismo código dos veces.

Documentación: https://europepmc.org/RestfulWebService

Misma estructura de siempre:
1. mapear_a_articulo()  -> traduce UN resultado a nuestro esquema
2. buscar()             -> llama a la API y devuelve la lista normalizada
"""

import requests

from adapters.base import articulo_vacio, guardar_metadata_raw

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def mapear_a_articulo(item: dict) -> dict:
    """
    Traduce un resultado crudo de Europe PMC a nuestro esquema normalizado.
    """
    articulo = articulo_vacio()

    articulo["fuente"] = "europepmc"
    articulo["titulo"] = item.get("title")
    articulo["resumen"] = item.get("abstractText")  # texto plano directo

    doi = item.get("doi")
    articulo["doi"] = f"https://doi.org/{doi}" if doi else None

    # PMID (PubMed ID) o PMCID como identificador de respaldo si no hay DOI
    articulo["identificador_externo"] = item.get("pmid") or item.get("pmcid")

    articulo["revista"] = item.get("journalTitle")

    # La fecha viene como "firstPublicationDate": "2023-05-10"
    fecha = item.get("firstPublicationDate")
    articulo["fecha_publicacion"] = fecha
    if fecha:
        articulo["anio_publicacion"] = int(fecha[:4])
    elif item.get("pubYear"):
        articulo["anio_publicacion"] = int(item["pubYear"])

    articulo["citas_count"] = item.get("citedByCount", 0)

    # isOpenAccess viene como texto "Y" o "N", no como booleano real
    articulo["tiene_texto_completo"] = item.get("isOpenAccess") == "Y"

    # Si tiene PMCID y es de acceso abierto, ese es el link al texto completo real
    pmcid = item.get("pmcid")
    if articulo["tiene_texto_completo"] and pmcid:
        articulo["url_fuente"] = f"https://europepmc.org/article/PMC/{pmcid.replace('PMC', '')}"
    elif articulo["doi"]:
        articulo["url_fuente"] = articulo["doi"]
    elif articulo["identificador_externo"]:
        articulo["url_fuente"] = f"https://europepmc.org/abstract/MED/{item.get('pmid')}"

    # Los autores vienen como un solo string separado por comas: "Pérez J, Gómez A."
    autor_string = item.get("authorString")
    if autor_string:
        articulo["autores"] = [nombre.strip() for nombre in autor_string.split(",")]

    guardar_metadata_raw(articulo, item)

    return articulo


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """
    Busca artículos en Europe PMC (incluye PubMed, PMC y preprints
    biomédicos) y devuelve la lista normalizada.

    Ejemplo de uso:
        resultados = buscar("microbioma ruminal metano", limite=5)
    """
    parametros = {
        "query": consulta,
        "format": "json",
        "pageSize": limite,
        "resultType": "core",  # "core" trae abstract y más detalle que "lite"
    }

    respuesta = requests.get(BASE_URL, params=parametros, timeout=15)
    respuesta.raise_for_status()

    datos = respuesta.json()
    items_crudos = datos.get("resultList", {}).get("result", [])

    return [mapear_a_articulo(item) for item in items_crudos]
