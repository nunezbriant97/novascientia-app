"""
Cliente de Hugging Face para generar imágenes con Flux Schnell.

Importante: Hugging Face reorganizó su API de inferencia en 2025-2026 bajo
el sistema "Inference Providers" -- ya no se llama directo a un endpoint
tipo api-inference.huggingface.co/models/... para modelos grandes como
Flux; ahora se enruta (por detrás) a proveedores como Together AI, Fal.ai
o Replicate, usando la librería oficial huggingface_hub en vez de
requests a mano.

Este módulo devuelve los BYTES crudos de una imagen (PNG), listos para
guardar en un archivo o subir a Mega.nz.

Documentación: https://huggingface.co/docs/inference-providers/en/tasks/text-to-image
"""

import io
import os

from huggingface_hub import InferenceClient

HUGGINGFACE_API_TOKEN = os.environ.get("HUGGINGFACE_API_TOKEN")

MODELO_FLUX = "black-forest-labs/FLUX.1-schnell"


def _obtener_cliente() -> InferenceClient:
    if not HUGGINGFACE_API_TOKEN:
        raise RuntimeError(
            "Falta HUGGINGFACE_API_TOKEN en el archivo .env. "
            "Conseguilo gratis en https://huggingface.co/settings/tokens"
        )
    # provider="auto" (default) deja que Hugging Face elija el proveedor
    # disponible más rápido/barato con crédito gratis en tu cuenta
    return InferenceClient(api_key=HUGGINGFACE_API_TOKEN)


def generar_imagen(prompt: str) -> bytes:
    """
    Genera una imagen a partir de una descripción en texto, usando Flux Schnell.

    Devuelve los bytes crudos de la imagen en formato PNG. Para guardarla
    a un archivo local, por ejemplo:

        imagen_bytes = generar_imagen("esquema de un sensor de humedad de suelo")
        with open("imagen.png", "wb") as archivo:
            archivo.write(imagen_bytes)

    Ejemplo de uso:
        imagen_bytes = generar_imagen("diagrama de un bioinsumo inteligente para cultivos")
    """
    cliente = _obtener_cliente()

    # client.text_to_image() devuelve un objeto PIL.Image, no bytes directo
    imagen_pil = cliente.text_to_image(prompt, model=MODELO_FLUX)

    buffer = io.BytesIO()
    imagen_pil.save(buffer, format="PNG")
    return buffer.getvalue()

