"""
Adapter de Crossref.

Crossref es la base de datos oficial de DOIs (casi todos los DOIs del
mundo se registran ahí). Es clave para nuestra deduplicación, porque
casi siempre tiene el DOI correcto y confiable.

Particularidad: para revistas "cerradas" (Nature, Science, Cell Press,
The Lancet), Crossref NO te da el texto completo -- solo título, autores,
revista y DOI. Eso está bien: en esos casos, tiene_texto_completo va a
quedar en False, y la app va a mostrar "ver en la fuente original" en
vez de "leer completo".

Documentación: https://api.crossref.org/swagger-ui/index.html

Misma estructura de siempre:
1. mapear_a_articulo()  -> traduce UN resultado a nuestro esquema
2. buscar()             -> llama a la API y devuelve la lista normalizada
"""

import requests

from adapters.base import articulo_vacio, guardar_metadata_raw

BASE_URL = "https://api.crossref.org/works"

# Igual que con OpenAlex, Crossref te da más velocidad si mandás un mail
# de contacto (su "polite pool").
MAIL_DE_CONTACTO = "tu-email@ejemplo.com"


def _armar_fecha(date_parts_dict: dict | None) -> str | None:
    """
    Crossref da las fechas en un formato raro:
        {"date-parts": [[2023, 5, 10]]}
    Esta función arma un string tipo "2023-05-10" a partir de eso.
    A veces solo viene el año, o el año y el mes -- lo manejamos igual.
    """
    if not date_parts_dict:
        return None

    partes = date_parts_dict.get("date-parts", [[]])[0]
    if not partes:
        return None

    # Rellenamos con "01" si falta mes o día
    anio = partes[0]
    mes = partes[1] if len(partes) > 1 else 1
    dia = partes[2] if len(partes) > 2 else 1

    return f"{anio:04d}-{mes:02d}-{dia:02d}"


def mapear_a_articulo(item: dict) -> dict:
    """
    Traduce un resultado crudo de Crossref a nuestro esquema normalizado.
    """
    articulo = articulo_vacio()

    articulo["fuente"] = "crossref"
    articulo["doi"] = f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else None
    articulo["identificador_externo"] = item.get("DOI")

    # El título viene en una lista (por temas históricos de la API), casi
    # siempre con un solo elemento
    titulos = item.get("title", [])
    articulo["titulo"] = titulos[0] if titulos else None

    # Crossref casi nunca da el abstract; cuando lo da, viene con etiquetas
    # JATS (formato XML de publicaciones científicas) que limpiamos un poco
    resumen_crudo = item.get("abstract")
    if resumen_crudo:
        articulo["resumen"] = (
            resumen_crudo.replace("<jats:p>", "").replace("</jats:p>", "").strip()
        )

    articulo["fecha_publicacion"] = _armar_fecha(item.get("published"))
    if articulo["fecha_publicacion"]:
        articulo["anio_publicacion"] = int(articulo["fecha_publicacion"][:4])

    # El nombre de la revista también viene en una lista
    revistas = item.get("container-title", [])
    articulo["revista"] = revistas[0] if revistas else None

    articulo["citas_count"] = item.get("is-referenced-by-count", 0)
    articulo["url_fuente"] = item.get("URL")

    # Licencia: Crossref a veces la trae en una lista "license"
    licencias = item.get("license", [])
    articulo["licencia"] = licencias[0].get("URL") if licencias else None

    # Crossref no dice directamente "es de acceso abierto"; lo inferimos:
    # si tiene licencia declarada, asumimos que es probable que sea abierto.
    # (No es 100% preciso -- lo ideal sería cruzar esto con OpenAlex más adelante)
    articulo["tiene_texto_completo"] = bool(licencias)

    # Los autores vienen como lista de {given, family}
    autores = []
    for autor in item.get("author", []):
        nombre_completo = f"{autor.get('given', '')} {autor.get('family', '')}".strip()
        if nombre_completo:
            autores.append(nombre_completo)
    articulo["autores"] = autores

    guardar_metadata_raw(articulo, item)

    return articulo


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """
    Busca artículos en Crossref y devuelve la lista normalizada.

    Ejemplo de uso:
        resultados = buscar("microbioma ruminal ganado bovino", limite=5)
    """
    parametros = {
        "query": consulta,
        "rows": limite,
        "mailto": MAIL_DE_CONTACTO,
    }

    respuesta = requests.get(BASE_URL, params=parametros, timeout=15)
    respuesta.raise_for_status()

    datos = respuesta.json()
    items_crudos = datos.get("message", {}).get("items", [])

    return [mapear_a_articulo(item) for item in items_crudos]


# Estas 6 fuentes de tu lista original no tienen (o no necesitan) un adapter
# propio: se cubren filtrando Crossref por el nombre de la revista/editorial.
# La clave es el nombre corto que usa el resto de la app; el valor es el
# nombre exacto que Crossref espera en el filtro "query.container-title".
EDITORIALES_VIA_CROSSREF = {
    "elife": "eLife",
    "bmc": "BMC",
    "frontiers": "Frontiers",
    "mdpi": "MDPI",
    "f1000research": "F1000Research",
    "peerj": "PeerJ",
}


def buscar_por_editorial(consulta: str, editorial: str, limite: int = 10) -> list[dict]:
    """
    Busca artículos en Crossref, pero limitados a una editorial/revista
    específica (eLife, BMC, Frontiers, MDPI, F1000Research o PeerJ).

    "editorial" tiene que ser una de las claves de EDITORIALES_VIA_CROSSREF,
    ej: "elife", "bmc", "frontiers", "mdpi", "f1000research", "peerj".

    Ejemplo de uso:
        resultados = buscar_por_editorial("biofertilizantes", "elife", limite=5)
    """
    if editorial not in EDITORIALES_VIA_CROSSREF:
        raise ValueError(
            f"Editorial '{editorial}' no soportada. "
            f"Opciones válidas: {list(EDITORIALES_VIA_CROSSREF.keys())}"
        )

    parametros = {
        "query": consulta,
        "query.container-title": EDITORIALES_VIA_CROSSREF[editorial],
        "rows": limite,
        "mailto": MAIL_DE_CONTACTO,
    }

    respuesta = requests.get(BASE_URL, params=parametros, timeout=15)
    respuesta.raise_for_status()

    datos = respuesta.json()
    items_crudos = datos.get("message", {}).get("items", [])

    articulos = [mapear_a_articulo(item) for item in items_crudos]

    # A diferencia de la búsqueda general, estas 6 editoriales son todas
    # de acceso abierto real -- forzamos tiene_texto_completo, aunque
    # Crossref no siempre declare la licencia explícitamente
    for articulo in articulos:
        articulo["tiene_texto_completo"] = True

    return articulos
