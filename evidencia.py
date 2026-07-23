"""
Evidencia real para el Núcleo IA.

Este módulo existe por un problema concreto que encontramos probando la
app: el chat general (groq_client.chat) no tenía ninguna herramienta de
búsqueda conectada, así que cuando alguien pedía referencias o "estado
del arte", el modelo directamente INVENTABA papers, autores y DOIs que
no existen -- algo grave para una herramienta de investigación.

La solución: antes de responder algo que necesite evidencia, buscamos de
verdad en las fuentes ya conectadas (mismos adapters que usa
/api/articulos/buscar) y le damos esos resúmenes reales al modelo como
contexto -- el mismo patrón que ya usábamos en generar_hipotesis().

Uso típico (desde groq_client.py):

    import evidencia

    if evidencia.necesita_evidencia(mensaje_usuario):
        resumenes = evidencia.buscar_evidencia(mensaje_usuario)
"""

import re

from adapters import crossref, europepmc, openalex
from database import get_connection, guardar_articulo

# Usamos solo estas 3 fuentes acá (no las 5 completas de /api/articulos/buscar):
# openalex y crossref son rápidas y confiables, europepmc suma buena
# cobertura biomédica/agrícola. semantic_scholar la dejamos afuera porque
# tiene un rate limit muy agresivo (429 frecuente) y esto corre en cada
# mensaje de chat que lo necesite, no solo cuando el usuario busca
# explícitamente -- no queremos que el chat se sienta lento por eso.
FUENTES_EVIDENCIA = {
    "openalex": openalex,
    "crossref": crossref,
    "europepmc": europepmc,
}

# Palabras que indican que la respuesta debería basarse en evidencia real
# (papers, estado del arte, autores, descubrimientos) y no solo en el
# conocimiento paramétrico del modelo. Si el mensaje no matchea ninguna,
# se responde directo (más rápido, y tiene sentido para preguntas de
# conocimiento general ya establecido, como pide SYSTEM_PROMPT_CHAT).
PALABRAS_CLAVE_EVIDENCIA = [
    "articulo", "artículo", "paper", "estudio", "investigacion", "investigación",
    "publicacion", "publicación", "revista", "doi", "cita", "citas", "referencia",
    "autor", "autores", "reciente", "recientes", "ultimos", "últimos", "avances",
    "descubrimiento", "descubrimientos", "estado del arte", "evidencia",
    "que dice la ciencia", "hay estudios", "se ha demostrado", "segun estudios",
    "según estudios",
]


def necesita_evidencia(mensaje: str) -> bool:
    """
    Heurística simple: ¿el mensaje pide algo que debería estar respaldado
    por literatura real, en vez de responderse solo de memoria?
    """
    texto = mensaje.lower()
    return any(palabra in texto for palabra in PALABRAS_CLAVE_EVIDENCIA)


def buscar_evidencia(consulta: str, limite_por_fuente: int = 3) -> list:
    """
    Busca artículos reales en las fuentes conectadas, los guarda en la
    base (con la misma deduplicación por DOI de siempre), y devuelve una
    lista de resúmenes en texto plano listos para pasarle como contexto
    al modelo.

    Si ninguna fuente encuentra nada (o todas fallan), devuelve una lista
    vacía -- eso le indica al modelo que tiene que admitir que no hay
    evidencia, en vez de inventar algo.
    """
    conn = get_connection()
    resumenes = []

    try:
        for adapter in FUENTES_EVIDENCIA.values():
            try:
                articulos_encontrados = adapter.buscar(consulta, limite_por_fuente)
            except Exception:
                # Si una fuente falla (rate limit, timeout, etc.), seguimos
                # con las demás -- no queremos que el chat se caiga por eso.
                continue

            for articulo in articulos_encontrados:
                guardar_articulo(conn, articulo)
                resumen = articulo.get("resumen")
                if resumen:
                    titulo = articulo.get("titulo", "Sin título")
                    anio = articulo.get("anio_publicacion", "s/f")
                    resumenes.append(f"[{titulo} ({anio})] {resumen}")

        conn.commit()
    finally:
        conn.close()

    return resumenes


def construir_mensaje_con_contexto(mensaje_usuario: str) -> str:
    """
    Punto de entrada principal: si el mensaje necesita evidencia, busca de
    verdad y arma un mensaje enriquecido con esa evidencia adjunta. Si no
    la necesita, devuelve el mensaje original sin tocar (para no gastar
    tiempo/cuota buscando en preguntas simples).
    """
    if not necesita_evidencia(mensaje_usuario):
        return mensaje_usuario

    resumenes = buscar_evidencia(mensaje_usuario)

    if not resumenes:
        return (
            f"{mensaje_usuario}\n\n"
            "(No se encontró evidencia en las fuentes conectadas para esta consulta. "
            "Si no tenés certeza respaldada por conocimiento ampliamente establecido, "
            "decilo explícitamente en vez de inventar referencias.)"
        )

    bloque_evidencia = "\n---\n".join(resumenes)
    return (
        f"{mensaje_usuario}\n\n"
        f"Evidencia real encontrada en fuentes académicas (usar SOLO estas citas, "
        f"no inventar ninguna otra):\n{bloque_evidencia}"
    )
