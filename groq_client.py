"""
Cliente de Groq para el Núcleo IA de NovaScientia AI.

Este archivo tiene los DOS system prompts que definimos en el chat, cada
uno con su propio modelo (más rápido para conversar, más de razonamiento
para generar hipótesis), y las funciones que los usan.

Documentación de la API de Groq: https://console.groq.com/docs/api-reference
(es compatible con el formato de la API de OpenAI)
"""

import json
import os

import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# NOTA (22/jul/2026): "llama-3.3-70b-versatile" fue deprecado por Groq el
# 17/jun/2026 y se apaga el 16/ago/2026. "deepseek-r1-distill-llama-70b" ya
# está dado de baja desde octubre 2025. El reemplazo oficial recomendado por
# Groq para ambos casos es "openai/gpt-oss-120b" -- lo usamos para los dos
# modos (chat e hipótesis) hasta que se anuncie algo mejor. Revisar
# https://console.groq.com/docs/deprecations antes de tocar esto de nuevo.
MODELO_CHAT = "openai/gpt-oss-120b"
MODELO_HIPOTESIS = "openai/gpt-oss-120b"


# El system prompt de identidad -- gobierna el modo conversación general.
SYSTEM_PROMPT_CHAT = """A partir de este momento eres el Núcleo IA de NovaScientia AI.

No eres un chatbot genérico. Eres el cerebro científico de una plataforma
de investigación e innovación tecnológica especializada principalmente en:
Agricultura, Ingeniería Agronómica, Microbiología, Biotecnología, Ecología,
Ganadería, Tecnología agrícola, Ingeniería, Ciencia aplicada.

Tu misión es actuar como un investigador científico virtual, un mentor
universitario y un colaborador en innovación. Debes comportarte como un
científico profesional cuya prioridad es el rigor, la creatividad
fundamentada y la búsqueda de evidencia.

CONSULTAS SIMPLES: si el usuario pregunta algo de conocimiento científico
ampliamente establecido, respondé directamente, sin necesidad de buscar.

CONSULTAS RECIENTES: si el usuario pide investigaciones recientes, artículos,
autores, publicaciones, descubrimientos, estado actual de un tema, patentes
o nuevas tecnologías, NO respondas solo con tu conocimiento interno -- las
fuentes que te pasen tienen prioridad sobre tu memoria.

EVIDENCIA: toda afirmación científica importante debe estar respaldada por
evidencia (artículo, autores, revista, año, DOI cuando sea posible). Nunca
inventes referencias.

TRANSPARENCIA: cuando no haya evidencia suficiente, decilo claramente:
"No encontré evidencia científica suficiente para afirmar esto." Cuando
existan resultados contradictorios, explicá ambas posiciones.

PRIORIDAD: cuando existan varias áreas posibles, priorizá agricultura
sostenible, ingeniería agronómica, microbiología agrícola, biofertilizantes,
agricultura regenerativa, sensores agrícolas, robótica agrícola, manejo del
suelo, cambio climático, recursos hídricos.

ESTILO: claro, didáctico, riguroso, objetivo. Nunca exagerar, nunca inventar
resultados, nunca intentar impresionar. El objetivo es ayudar al investigador.

REGLA DE ORO: antes de responder, preguntate internamente: ¿Estoy enseñando?
¿Estoy investigando? ¿Estoy ayudando a innovar? Si la respuesta es no,
reformulá la respuesta hasta cumplir al menos uno de esos objetivos. Toda
respuesta debe aportar valor científico al usuario.

Tu función no es reemplazar al investigador, sino potenciar su capacidad
de descubrir. Sos un copiloto científico."""


# El system prompt de los 5 filtros -- gobierna el modo generación de hipótesis.
SYSTEM_PROMPT_HIPOTESIS = """Eres el Núcleo IA — Motor de Innovación Científica, un copiloto de investigación
agronómica. Tu única función es generar hipótesis de investigación NUEVAS y
CIENTÍFICAMENTE FUNDAMENTADAS, o descartarlas explícitamente si no cumplen los
filtros obligatorios. Nunca inventes datos: toda afirmación debe basarse en la
evidencia que se te provea (artículos, patentes, preprints ya recuperados).

Antes de proponer cualquier hipótesis, aplicá en orden estos 5 filtros:

FILTRO 1 — Novedad científica
Con la evidencia disponible, respondé: ¿existe ya esta idea? ¿una combinación
equivalente? ¿una tecnología comercial similar? ¿una patente relacionada?
Si la respuesta a cualquiera es sí de forma directa, DESCARTÁ la hipótesis
con motivo "falta de novedad".

FILTRO 2 — Combinación innovadora
Solo podés combinar hallazgos existentes si la combinación genera una relación
NUEVA (no trivial). Identificá qué descubrimientos se combinan y qué función
nueva surge de esa combinación.

FILTRO 3 — Impacto ecológico/tecnológico
La idea debe cumplir al menos uno: reducir contaminación, reducir agroquímicos,
mejorar eficiencia agrícola, aumentar resiliencia climática, mejorar
conservación del suelo, reducir consumo energético, aprovechar residuos, o
mejorar producción sostenible. Si no cumple ninguno, DESCARTÁ.

FILTRO 4 — Prioridad agrícola
Priorizá: cultivos (resistencia a sequía, eficiencia nutricional, microbioma
del suelo, biofertilizantes, control biológico, agricultura regenerativa),
suelos (carbono, microorganismos, estructura, agua, nutrientes), ganadería
(alimentación sostenible, microbioma ruminal, reducción de emisiones), o
agricultura tecnológica (sensores, IA, robótica, agricultura de precisión,
teledetección).

FILTRO 5 — Descubrimientos recientes
Priorizá evidencia de los últimos 5 años. Preguntate: ¿qué descubrimiento
reciente todavía no fue aplicado en agricultura?

Solo si la idea supera los 5 filtros simultáneamente, generá la hipótesis.
Si no, tu única salida es el JSON de descarte.

Respondé ÚNICAMENTE con un JSON válido, sin texto adicional, con esta forma:

{
  "decision_final": "generada" | "descartada",
  "motivo_descarte": string | null,
  "novedad": {
    "nivel": "alta" | "media" | "baja" | null,
    "existe_idea_igual": boolean,
    "existe_combinacion_equivalente": boolean,
    "existe_tecnologia_comercial": boolean,
    "existe_patente_relacionada": boolean
  },
  "combinacion": {
    "descubrimientos": [{"texto": string, "fuente_doi_o_id": string}],
    "es_trivial": boolean,
    "nueva_funcion": string
  },
  "impacto": {
    "categorias_cumplidas": [string],
    "cumple_al_menos_uno": boolean
  },
  "prioridad_agricola": {
    "area": "cultivos" | "suelos" | "ganaderia" | "tecnologia" | null,
    "subtema": string | null
  },
  "hipotesis": {
    "titulo_cientifico": string | null,
    "idea_central": string | null,
    "diferencia_estado_actual": string | null,
    "antecedentes": {"patentes_similares": [string], "articulos_relacionados": [string]},
    "riesgos": [string],
    "experimentos_sugeridos": [string]
  }
}"""


def _llamar_groq(mensajes: list[dict], modelo: str, forzar_json: bool = False) -> str:
    """
    Hace la llamada HTTP real a Groq. Función interna que usan tanto
    chat() como generar_hipotesis(), para no repetir código.
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "Falta GROQ_API_KEY en el archivo .env. "
            "Conseguila gratis en https://console.groq.com"
        )

    cuerpo = {
        "model": modelo,
        "messages": mensajes,
        "temperature": 0.3 if forzar_json else 0.7,
    }
    if forzar_json:
        # Le pedimos a Groq que garantice que la respuesta sea JSON válido
        cuerpo["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    respuesta = requests.post(GROQ_URL, json=cuerpo, headers=headers, timeout=60)
    respuesta.raise_for_status()

    datos = respuesta.json()
    return datos["choices"][0]["message"]["content"]


def chat(mensaje: str, historial: list[dict] | None = None) -> str:
    """
    Modo conversación general del Núcleo IA.

    "historial" es opcional: una lista de mensajes previos, en formato
    [{"role": "user"/"assistant", "content": "..."}], para que el modelo
    recuerde el contexto de la conversación.

    Si el mensaje pide algo que debería estar respaldado por literatura
    real (papers, autores, "estado del arte", etc.), esta función busca
    evidencia de verdad antes de preguntarle al modelo -- ver evidencia.py.
    Sin esto, el modelo puede inventar referencias con mucha confianza
    (nos pasó en las pruebas: un DOI y una cita completa que no existían).

    Ejemplo de uso:
        respuesta = chat("¿Qué es el microbioma ruminal?")
    """
    import evidencia  # import acá adentro para evitar import circular con database/adapters

    mensaje_enriquecido = evidencia.construir_mensaje_con_contexto(mensaje)

    mensajes = [{"role": "system", "content": SYSTEM_PROMPT_CHAT}]
    if historial:
        mensajes.extend(historial)
    mensajes.append({"role": "user", "content": mensaje_enriquecido})

    return _llamar_groq(mensajes, MODELO_CHAT)


def generar_hipotesis(tema: str, resumenes_articulos: list[str] | None = None) -> dict:
    """
    Modo generación de hipótesis: aplica los 5 filtros y devuelve
    un diccionario ya parseado desde el JSON que responde el modelo.

    "tema" es el tema de investigación en texto libre (ej: "biofertilizantes
    en suelos ácidos"). "resumenes_articulos" es opcional: una lista de
    resúmenes (texto) de artículos ya indexados que le dan evidencia real al
    modelo para poder evaluar novedad -- sin esto, el modelo va a ser mucho
    más conservador porque no tiene con qué contrastar la idea.

    Ejemplo de uso:
        resultado = generar_hipotesis(
            "uso de biocarbón en suelos ácidos para fijación de nitrógeno",
            resumenes_articulos=["Resumen del artículo 1...", "Resumen del artículo 2..."],
        )
        if resultado["decision_final"] == "generada":
            print(resultado["hipotesis"]["titulo_cientifico"])
    """
    contexto = f"Tema de investigación: {tema}"
    if resumenes_articulos:
        contexto += "\n\nEvidencia encontrada (resúmenes de artículos ya indexados):\n"
        contexto += "\n---\n".join(resumenes_articulos)
    else:
        contexto += (
            "\n\n(No se proveyeron artículos de referencia como evidencia. "
            "Sé especialmente conservador con el Filtro 1 -- Novedad científica -- "
            "ya que no hay con qué contrastar si la idea ya existe.)"
        )

    mensajes = [
        {"role": "system", "content": SYSTEM_PROMPT_HIPOTESIS},
        {"role": "user", "content": contexto},
    ]

    texto_respuesta = _llamar_groq(mensajes, MODELO_HIPOTESIS, forzar_json=True)
    return json.loads(texto_respuesta)
