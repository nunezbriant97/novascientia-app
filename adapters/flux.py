"""
Adapter de Hugging Face Inference API para generar imágenes con FLUX.1-schnell.

FLUX.1-schnell es la versión open-source y gratuita de FLUX (licencia
Apache 2.0, permite uso personal/científico/comercial). La usamos vía la
Inference API de Hugging Face, que da una cuota gratuita mensual --
de sobra para el volumen que necesitamos (unas pocas imágenes por proyecto).

Si en algún momento se necesita más calidad (texto más nítido, más
fotorrealismo), la migración a FLUX Pro de Black Forest Labs (pago) es
directa: solo hay que cambiar esta función, el resto de la app no se entera.

Documentación: https://huggingface.co/docs/inference-providers
"""

import os
import time

import requests

API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"

HF_TOKEN = os.environ.get("HUGGINGFACE_API_TOKEN")

# Cuántas veces reintentar si el modelo todavía se está "despertando".
# La Inference API gratuita apaga los modelos que no se usan seguido y
# tarda unos segundos en volver a cargarlos -- mientras tanto devuelve 503.
REINTENTOS_MAXIMOS = 5
ESPERA_ENTRE_REINTENTOS_SEG = 8


def generar_imagen(prompt: str, ancho: int = 1024, alto: int = 1024) -> bytes:
    """
    Genera una imagen con FLUX.1-schnell a partir de un prompt en texto.

    Devuelve los bytes crudos de la imagen (PNG), listos para guardar en
    disco o subir a un storage externo (Mega, etc.).

    Lanza RuntimeError si falta el token, o si la API sigue fallando
    después de todos los reintentos.

    Ejemplo de uso:
        imagen_bytes = generar_imagen("A quartz tube reactor with purple plasma...")
        with open("salida.png", "wb") as f:
            f.write(imagen_bytes)
    """
    if not HF_TOKEN:
        raise RuntimeError(
            "Falta HUGGINGFACE_API_TOKEN en el archivo .env. "
            "Conseguilo gratis en https://huggingface.co/settings/tokens "
            "(con permiso de lectura alcanza)."
        )

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": ancho,
            "height": alto,
        },
    }

    ultimo_error = None
    for intento in range(1, REINTENTOS_MAXIMOS + 1):
        respuesta = requests.post(API_URL, headers=headers, json=payload, timeout=120)

        if respuesta.status_code == 200:
            return respuesta.content

        if respuesta.status_code == 503:
            # El modelo se está cargando del lado de Hugging Face (común en
            # el tier gratuito cuando no se usó hace un rato) -- reintentamos.
            ultimo_error = f"Modelo cargando (intento {intento}/{REINTENTOS_MAXIMOS})"
            time.sleep(ESPERA_ENTRE_REINTENTOS_SEG)
            continue

        # Cualquier otro error (401 token inválido, 429 límite excedido, etc.)
        # no tiene sentido reintentarlo -- cortamos ahí.
        raise RuntimeError(
            f"Error generando imagen con FLUX.1-schnell "
            f"(status {respuesta.status_code}): {respuesta.text[:300]}"
        )

    raise RuntimeError(f"FLUX.1-schnell no respondió a tiempo: {ultimo_error}")
