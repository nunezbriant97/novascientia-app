"""
Adapter de OpenAlex.

OpenAlex es gratis, no pide API key, y cubre casi toda la ciencia publicada.
Documentación: https://docs.openalex.org/

Este archivo tiene 3 partes:
1. reconstruir_resumen()   -> arregla el formato raro del abstract
2. mapear_a_articulo()     -> traduce UN resultado de OpenAlex a nuestro esquema
3. buscar()                -> llama a la API y devuelve una lista de artículos normalizados
"""

import requests

from adapters.base import articulo_vacio, guardar_metadata_raw

BASE_URL = "https://api.openalex.org/works"

# OpenAlex pide (no obliga, pero lo recomiendan fuerte) que mandes un mail
# de contacto en la consulta, para entrar en su "polite pool" con más velocidad.
# Poné tu propio mail acá cuando lo pruebes.
MAIL_DE_CONTACTO = "tu-email@ejemplo.com"


def reconstruir_resumen(abstract_inverted_index: dict | None) -> str | None:
    """
    OpenAlex no te da el abstract como texto plano por temas de derechos de autor.
    En cambio, te da un diccionario tipo:

        {"El": [0], "suelo": [1, 5], "es": [2], ...}

    Donde cada palabra apunta a en qué posición (o posiciones) aparece.
    Esta función arma de nuevo la oración original a partir de eso.
    """
    if not abstract_inverted_index:
        return None

    # Armamos una lista donde el índice = posición de la palabra en la oración
    posiciones_totales = max(
        pos for posiciones in abstract_inverted_index.values() for pos in posiciones
    )
    palabras_ordenadas = [""] * (posiciones_totales + 1)

    for palabra, posiciones in abstract_inverted_index.items():
        for pos in posiciones:
            palabras_ordenadas[pos] = palabra

    return " ".join(palabras_ordenadas)


def mapear_a_articulo(item: dict) -> dict:
    """
    Toma UN resultado crudo de la API de OpenAlex y lo traduce
    a nuestro esquema normalizado (el mismo de la tabla `articulos`).
    """
    articulo = articulo_vacio()

    articulo["fuente"] = "openalex"
    articulo["doi"] = item.get("doi")  # viene como "https://doi.org/10.xxxx"
    articulo["identificador_externo"] = item.get("id")  # ej: "https://openalex.org/W123..."
    articulo["titulo"] = item.get("title")
    articulo["resumen"] = reconstruir_resumen(item.get("abstract_inverted_index"))
    articulo["anio_publicacion"] = item.get("publication_year")
    articulo["fecha_publicacion"] = item.get("publication_date")
    articulo["citas_count"] = item.get("cited_by_count", 0)

    # La revista/journal está anidada dentro de primary_location.source
    ubicacion_principal = item.get("primary_location") or {}
    fuente_info = ubicacion_principal.get("source") or {}
    articulo["revista"] = fuente_info.get("display_name")

    # Acceso abierto: OpenAlex ya nos dice si hay texto completo disponible
    open_access = item.get("open_access") or {}
    articulo["tiene_texto_completo"] = bool(open_access.get("is_oa"))
    articulo["url_fuente"] = open_access.get("oa_url") or ubicacion_principal.get("landing_page_url")
    articulo["licencia"] = ubicacion_principal.get("license")

    # Los autores vienen en una lista de "authorships"
    autores = []
    for authorship in item.get("authorships", []):
        nombre = (authorship.get("author") or {}).get("display_name")
        if nombre:
            autores.append(nombre)
    articulo["autores"] = autores

    guardar_metadata_raw(articulo, item)

    return articulo


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """
    Busca artículos en OpenAlex y devuelve una lista de artículos
    YA normalizados (listos para guardar en la tabla `articulos`).

    Ejemplo de uso:
        resultados = buscar("microbioma del suelo en cultivos de soja", limite=5)
    """
    parametros = {
        "search": consulta,
        "per_page": limite,
        "mailto": MAIL_DE_CONTACTO,
    }

    respuesta = requests.get(BASE_URL, params=parametros, timeout=15)
    respuesta.raise_for_status()  # si la API falla, esto avisa con un error claro

    datos = respuesta.json()
    items_crudos = datos.get("results", [])

    return [mapear_a_articulo(item) for item in items_crudos]


# --------------------------------------------------------------------------
# Búsqueda de AUTORES (reemplaza lo que iba a hacer el endpoint de ORCID).
#
# OpenAlex ya tiene su propio catálogo de autores, gratis y sin necesidad
# de credenciales -- incluye el ORCID de cada autor cuando lo tiene, así
# que no perdemos esa info, solo cambiamos de dónde la sacamos.
# Documentación: https://docs.openalex.org/api-entities/authors
# --------------------------------------------------------------------------

BASE_URL_AUTORES = "https://api.openalex.org/authors"


def mapear_a_autor(item: dict) -> dict:
    """
    Toma UN resultado crudo de la API de Authors de OpenAlex y lo traduce
    a nuestro esquema normalizado (el mismo de la tabla `autores`).
    """
    autor = {
        "nombre_completo": item.get("display_name"),
        "orcid": None,
        "semantic_scholar_id": None,
        "institucion": None,
        "pais": None,
        "area_especialidad": None,
        "h_index": None,
        "citas_totales": item.get("cited_by_count"),
        "publicaciones_count": item.get("works_count"),
        "metadata_raw": None,
    }

    # El orcid viene como URL completa ("https://orcid.org/0000-...") --
    # nos quedamos solo con el identificador, que es lo que usamos como
    # clave única en la tabla.
    orcid_url = item.get("orcid")
    if orcid_url:
        autor["orcid"] = orcid_url.rsplit("/", 1)[-1]

    # Última institución conocida (puede no estar si el autor no publicó
    # nada recientemente con afiliación declarada).
    instituciones = item.get("last_known_institutions") or []
    if instituciones:
        primera = instituciones[0]
        autor["institucion"] = primera.get("display_name")
        autor["pais"] = primera.get("country_code")

    # Área de especialidad: OpenAlex la infiere a partir de los temas
    # ("topics") de los papers del autor. Nos quedamos con el más frecuente.
    topics = item.get("topics") or []
    if topics:
        autor["area_especialidad"] = topics[0].get("display_name")

    # h_index vive adentro de summary_stats
    resumen_stats = item.get("summary_stats") or {}
    autor["h_index"] = resumen_stats.get("h_index")

    guardar_metadata_raw(autor, item)

    return autor


def buscar_autores(consulta: str, limite: int = 10) -> list[dict]:
    """
    Busca investigadores por nombre en OpenAlex y devuelve una lista de
    autores YA normalizados (listos para guardar en la tabla `autores`).

    Reemplaza la función que iba a cumplir ORCID en el diseño original --
    misma info (nombre, orcid, institución, h-index, publicaciones), pero
    sin necesitar credenciales ni pasar por el registro de Developer Tools.

    Ejemplo de uso:
        resultados = buscar_autores("Carlos Bravo suelo Ecuador", limite=5)
    """
    parametros = {
        "search": consulta,
        "per_page": limite,
        "mailto": MAIL_DE_CONTACTO,
    }

    respuesta = requests.get(BASE_URL_AUTORES, params=parametros, timeout=15)
    respuesta.raise_for_status()

    datos = respuesta.json()
    items_crudos = datos.get("results", [])

    return [mapear_a_autor(item) for item in items_crudos]
