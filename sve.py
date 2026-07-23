"""
Scientific Visual Engine (SVE).

Este módulo conecta tres piezas:
1. La conversación científica del proyecto, guardada en `proyecto_mensaje`
   (SQLite) -- así el contexto sobrevive aunque se cierre el navegador.
2. groq_client.py (el Núcleo IA -- mismo cliente y modelos que usa el chat
   general y la generación de hipótesis) para analizar esa conversación y
   transformarla en un prompt detallado para imágenes.
3. adapters/flux.py para generar la imagen final con FLUX.1-schnell.

Flujo típico:
    responder_mensaje(1, "hablemos de un reactor de plasma...")
        -> guarda el mensaje, responde como Núcleo IA, guarda la respuesta

    responder_mensaje(1, "dibújalo")
        -> detecta la frase disparadora, en vez de responder con texto
           dispara generar_visualizacion() y devuelve la imagen

    generar_visualizacion(conn, 1)
        -> se puede llamar directo también (ej: botón "Generar imagen" en el frontend)
"""

import json
import os
import unicodedata

from adapters import flux
from database import get_connection
import groq_client

# Frases que disparan la generación de imagen en vez de una respuesta de texto.
# Basado en prompt_flux.txt -- se puede seguir ampliando esta lista.
FRASES_DISPARADORAS = [
    "dibuj", "haz un render", "hazme un render", "genera una imagen",
    "generá una imagen", "muéstrame cómo quedaría", "muestrame como quedaria",
    "quiero verlo", "diseñalo", "diseñálo", "crear ilustración",
    "crea una ilustracion", "crear infografía", "crea una infografia",
    "crear plano", "crea un plano", "crear esquema", "crea un esquema",
    "renderizalo", "renderízalo", "hazme un dibujo", "hazme el dibujo",
]

ESTILOS_SOPORTADOS = {
    "engineering_blueprint": "Engineering Blueprint (plano técnico de ingeniería)",
    "scientific_infographic": "Scientific Infographic (estilo Nature/Joule)",
    "patent_drawing": "Patent Drawing (estilo dibujo de patente)",
    "photorealistic_prototype": "Photorealistic Prototype (render hiperrealista)",
    "exploded_view": "Exploded View (vista explotada)",
    "cutaway_view": "Cutaway View (corte transversal)",
    "laboratory_concept": "Laboratory Concept",
    "industrial_design": "Industrial Design",
    "medical_device": "Medical Device",
    "agricultural_innovation": "Agricultural Innovation",
}


def _sin_acentos(texto: str) -> str:
    """Quita tildes/diacríticos para que la detección no dependa de si el
    usuario escribió "dibújalo" o "dibujalo", "generá" o "genera", etc."""
    forma_descompuesta = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in forma_descompuesta if not unicodedata.combining(c))


def es_pedido_de_imagen(texto: str) -> bool:
    """Detecta si el mensaje del usuario está pidiendo generar la imagen."""
    texto_normalizado = _sin_acentos(texto.lower())
    return any(_sin_acentos(frase) in texto_normalizado for frase in FRASES_DISPARADORAS)


def guardar_mensaje(conn, proyecto_id: int, rol: str, contenido: str) -> int:
    """Guarda un turno de la conversación. rol: 'usuario' o 'asistente'."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO proyecto_mensaje (proyecto_id, rol, contenido) VALUES (?, ?, ?)",
        (proyecto_id, rol, contenido),
    )
    conn.commit()
    return cursor.lastrowid


def obtener_historial(conn, proyecto_id: int) -> list:
    """Devuelve toda la conversación de un proyecto, en orden cronológico."""
    filas = conn.execute(
        "SELECT rol, contenido, fecha FROM proyecto_mensaje "
        "WHERE proyecto_id = ? ORDER BY fecha ASC",
        (proyecto_id,),
    ).fetchall()
    return [dict(fila) for fila in filas]


def responder_mensaje(proyecto_id: int, mensaje_usuario: str) -> dict:
    """
    Procesa un turno de la charla científica del proyecto.

    Caso normal: guarda el mensaje del usuario, le pide al Núcleo IA
    (groq_client, mismo prompt que el chat general) una respuesta con
    todo el historial del proyecto como contexto, la guarda, y la devuelve.

    Caso "dibújalo": si el mensaje pide explícitamente una imagen, en vez
    de responder con texto dispara generar_visualizacion() y devuelve la
    imagen generada.
    """
    conn = get_connection()
    try:
        guardar_mensaje(conn, proyecto_id, "usuario", mensaje_usuario)

        if es_pedido_de_imagen(mensaje_usuario):
            resultado = generar_visualizacion(conn, proyecto_id)
            resumen = f"Generé la visualización del proyecto (estilo: {resultado['estilo']})."
            guardar_mensaje(conn, proyecto_id, "asistente", resumen)
            return {"tipo": "imagen", **resultado}

        historial = obtener_historial(conn, proyecto_id)
        historial_para_groq = [
            {"role": "assistant" if m["rol"] == "asistente" else "user", "content": m["contenido"]}
            for m in historial[:-1]  # el último ya lo mandamos aparte como "mensaje"
        ]

        texto_respuesta = groq_client.chat(mensaje_usuario, historial_para_groq)
        guardar_mensaje(conn, proyecto_id, "asistente", texto_respuesta)

        return {"tipo": "texto", "respuesta": texto_respuesta}
    finally:
        conn.close()


def _elegir_estilo_automatico(descripcion_proyecto: str) -> str:
    """Estilo por defecto (si la IA no elige uno válido), según prompt_flux.txt."""
    texto = (descripcion_proyecto or "").lower()
    if "reactor" in texto or "quimic" in texto or "proceso" in texto:
        return "scientific_infographic"
    if "dispositivo" in texto or "electron" in texto or "circuito" in texto:
        return "exploded_view"
    if "maquina" in texto or "máquina" in texto or "mecanis" in texto:
        return "engineering_blueprint"
    return "scientific_infographic"


SYSTEM_PROMPT_SVE = """Sos el "Scientific Visual Engine" de NovaScientia AI. Tu trabajo es
analizar una conversación científica/técnica completa y transformarla en
UN objeto JSON que se va a usar para generar una imagen con FLUX.

Estilos disponibles (elegí el que mejor encaje si el usuario no pidió uno):
{lista_estilos}

Devolvé SOLO un objeto JSON (sin texto adicional, sin markdown, sin backticks)
con esta forma exacta:
{{
  "titulo": "string, nombre corto del proyecto",
  "descripcion": "string, 1-2 frases resumiendo qué es el proyecto",
  "estilo": "una de las claves de estilo de arriba",
  "prompt_flux": "string MUY detallado en inglés (FLUX entiende mejor en inglés) describiendo materiales, formas, texturas, componentes, colores, perspectiva, iluminación, anotaciones/etiquetas técnicas, nivel de ingeniería, tipo de infografía y nivel de detalle. Nunca una frase corta -- varios párrafos si hace falta."
}}

El prompt_flux debe incluir, cuando corresponda porque el proyecto es
científico: etiquetas, flechas, flujos, entradas, salidas, materiales,
temperaturas, presiones, reacciones químicas, vistas (frontal/lateral/superior),
leyenda y notas técnicas -- como en infografías científicas profesionales
(estilo Nature, Joule)."""


def _construir_prompt_flux(conn, proyecto_id: int) -> dict:
    """
    Le pide al Núcleo IA que analice TODA la conversación del proyecto y
    arme un objeto JSON con el modelo estructurado del proyecto + un
    prompt detallado listo para mandarle a FLUX.

    Sigue la lógica de estilos y nivel de detalle de prompt_flux.txt.
    """
    historial = obtener_historial(conn, proyecto_id)
    if not historial:
        raise RuntimeError(
            "Este proyecto todavía no tiene conversación guardada -- "
            "no hay nada que visualizar todavía."
        )

    conversacion_texto = "\n".join(
        f"{'Usuario' if m['rol'] == 'usuario' else 'IA'}: {m['contenido']}"
        for m in historial
    )

    lista_estilos = "\n".join(f"- {clave}: {desc}" for clave, desc in ESTILOS_SOPORTADOS.items())
    system_prompt = SYSTEM_PROMPT_SVE.format(lista_estilos=lista_estilos)

    respuesta_json = groq_client._llamar_groq(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Conversación completa del proyecto:\n\n{conversacion_texto}"},
        ],
        groq_client.MODELO_HIPOTESIS,  # el modelo de razonamiento (gpt-oss-120b), no el de chat rápido
        forzar_json=True,
    )

    modelo = json.loads(respuesta_json)

    if modelo.get("estilo") not in ESTILOS_SOPORTADOS:
        modelo["estilo"] = _elegir_estilo_automatico(modelo.get("descripcion", ""))

    return modelo


def generar_visualizacion(conn, proyecto_id: int) -> dict:
    """
    Genera la imagen final del proyecto:
    1. Analiza toda la conversación y arma el prompt para FLUX (Núcleo IA).
    2. Llama a FLUX.1-schnell (Hugging Face) para generar la imagen.
    3. Guarda el archivo en static/generadas/ y registra la referencia
       en `archivos_temporales`.

    Devuelve un dict con la info de la imagen generada.
    """
    modelo = _construir_prompt_flux(conn, proyecto_id)

    imagen_bytes = flux.generar_imagen(modelo["prompt_flux"])

    carpeta_salida = os.path.join("static", "generadas")
    os.makedirs(carpeta_salida, exist_ok=True)
    nombre_archivo = f"proyecto_{proyecto_id}_{modelo['estilo']}.png"
    ruta_local = os.path.join(carpeta_salida, nombre_archivo)
    with open(ruta_local, "wb") as f:
        f.write(imagen_bytes)

    # NOTA: archivos_temporales pide mega_node_id NOT NULL porque el diseño
    # original preveía subir todo a Mega.nz para que persista más allá del
    # disco local. Hasta que se conecte ese adapter, guardamos un
    # placeholder acá y la ruta local real queda en 'metadata' para no
    # perder el archivo -- cuando esté Mega, solo hay que llenar ese campo.
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO archivos_temporales (
            tipo, entidad_tipo, entidad_id, mega_node_id, nombre_archivo,
            metadata, fecha_expiracion
        ) VALUES ('imagen', 'proyecto', ?, ?, ?, ?, datetime('now', '+30 days'))
        """,
        (
            proyecto_id,
            "pendiente_mega",
            nombre_archivo,
            json.dumps({
                "ruta_local": ruta_local,
                "titulo": modelo["titulo"],
                "estilo": modelo["estilo"],
            }, ensure_ascii=False),
        ),
    )
    conn.commit()

    return {
        "titulo": modelo["titulo"],
        "descripcion": modelo["descripcion"],
        "estilo": modelo["estilo"],
        "prompt_usado": modelo["prompt_flux"],
        "ruta_local": ruta_local,
        "url": "/" + ruta_local.replace(os.sep, "/"),
    }
