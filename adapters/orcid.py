"""
Adapter de ORCID.

A diferencia de los adapters anteriores, este NO busca artículos --
busca AUTORES/investigadores, y por eso su forma de traducir datos
apunta a la tabla `autores` que diseñamos, no a `articulos`.

Otra diferencia importante: ORCID pide autenticación (gratis, pero
necesitás un client_id y client_secret propios, ver instrucciones
en el chat). Esto funciona con OAuth2: antes de buscar, le pedimos
a ORCID un "token" temporal usando esas credenciales.

Documentación: https://info.orcid.org/documentation/features/public-api/

Este archivo tiene 4 partes:
1. obtener_token()       -> pide el token de acceso a ORCID (se reusa mientras dure)
2. mapear_a_autor()      -> traduce UN resultado a nuestro esquema de autor
3. buscar()              -> busca investigadores por nombre/palabra clave
4. obtener_perfil()      -> trae detalle de UN investigador (institución, etc.)
"""

import os
import time

import requests

TOKEN_URL = "https://orcid.org/oauth/token"
BUSQUEDA_URL = "https://pub.orcid.org/v3.0/search/"
PERFIL_URL = "https://pub.orcid.org/v3.0/{orcid_id}/record"

# Estas dos claves NUNCA van hardcodeadas -- se leen del archivo .env
CLIENT_ID = os.environ.get("ORCID_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ORCID_CLIENT_SECRET")

# Guardamos el token en memoria para no pedir uno nuevo en cada búsqueda
# (ORCID te da un token que dura varios años, así que alcanza con pedirlo
# una sola vez por vez que se reinicie el servidor)
_token_cache = {"access_token": None, "expira_en": 0}


def obtener_token() -> str:
    """
    Pide (o reutiliza) un token de acceso de ORCID.
    Si ya tenemos uno vigente en memoria, lo devuelve directo sin
    volver a pedirle nada a ORCID.
    """
    ahora = time.time()

    if _token_cache["access_token"] and ahora < _token_cache["expira_en"]:
        return _token_cache["access_token"]

    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "Faltan ORCID_CLIENT_ID y ORCID_CLIENT_SECRET en el archivo .env. "
            "Registrate en https://orcid.org/developer-tools para conseguirlos."
        )

    respuesta = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "/read-public",
        },
        headers={"Accept": "application/json"},
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()

    _token_cache["access_token"] = datos["access_token"]
    # Le restamos 60 segundos de margen por las dudas
    _token_cache["expira_en"] = ahora + datos.get("expires_in", 3600) - 60

    return _token_cache["access_token"]


def mapear_a_autor(orcid_id: str, given_names: str | None, family_name: str | None) -> dict:
    """
    Arma un autor normalizado a partir de los datos básicos de la búsqueda.
    (Para institución/país hace falta llamar a obtener_perfil() aparte,
    porque la búsqueda no los trae para no hacer la respuesta pesada.)
    """
    nombre_completo = f"{given_names or ''} {family_name or ''}".strip()

    return {
        "orcid": orcid_id,
        "nombre_completo": nombre_completo or None,
        "institucion": None,
        "pais": None,
        "area_especialidad": None,
        "h_index": None,
        "citas_totales": None,
        "publicaciones_count": None,
    }


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """
    Busca investigadores por nombre o palabra clave.
    Devuelve datos básicos (nombre + ORCID); para el perfil completo
    de uno en particular, usá obtener_perfil(orcid_id) después.

    Ejemplo de uso:
        resultados = buscar("microbioma suelo agronomia", limite=5)
    """
    token = obtener_token()

    parametros = {"q": consulta, "rows": limite}
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    respuesta = requests.get(BUSQUEDA_URL, params=parametros, headers=headers, timeout=15)
    respuesta.raise_for_status()

    datos = respuesta.json()
    resultados_crudos = datos.get("result", []) or []

    autores = []
    for item in resultados_crudos:
        orcid_id = item.get("orcid-identifier", {}).get("path")
        if orcid_id:
            # La búsqueda general de ORCID no siempre trae el nombre --
            # para eso conviene llamar a obtener_perfil() con el orcid_id
            autores.append(mapear_a_autor(orcid_id, None, None))

    return autores


def _extraer_perfil_de_json(orcid_id: str, datos: dict) -> dict:
    """
    Toma el JSON crudo que devuelve ORCID para un perfil y arma el autor
    normalizado. Separada de obtener_perfil() para poder probarla sin
    necesidad de llamar a la API real.
    """
    persona = datos.get("person", {}) or {}
    nombre_info = persona.get("name", {}) or {}
    given_names = (nombre_info.get("given-names") or {}).get("value")
    family_name = (nombre_info.get("family-name") or {}).get("value")

    autor = mapear_a_autor(orcid_id, given_names, family_name)

    # El empleo más reciente nos da institución y país
    actividades = datos.get("activities-summary", {}) or {}
    empleos = (actividades.get("employments", {}) or {}).get("affiliation-group", [])
    if empleos:
        resumen_empleo = empleos[0].get("summaries", [{}])[0].get("employment-summary", {})
        autor["institucion"] = resumen_empleo.get("organization", {}).get("name")
        autor["pais"] = (
            resumen_empleo.get("organization", {}).get("address", {}).get("country")
        )

    return autor


def obtener_perfil(orcid_id: str) -> dict:
    """
    Trae el perfil completo de UN investigador: nombre, institución
    (empleo más reciente declarado), y país.

    Ejemplo de uso:
        perfil = obtener_perfil("0000-0002-1825-0097")
    """
    token = obtener_token()
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    url = PERFIL_URL.format(orcid_id=orcid_id)
    respuesta = requests.get(url, headers=headers, timeout=15)
    respuesta.raise_for_status()
    datos = respuesta.json()

    return _extraer_perfil_de_json(orcid_id, datos)
