"""
Prueba imagen_client.py SIN llamar a la API real de Hugging Face
(para eso hace falta HUGGINGFACE_API_TOKEN real).
"""

import io

from PIL import Image

import imagen_client


def _imagen_pil_de_prueba() -> Image.Image:
    """Crea una imagen mínima de 2x2 píxeles en memoria, para no depender de un archivo real."""
    return Image.new("RGB", (2, 2), color="red")


def test_falta_token_lanza_error(monkeypatch):
    monkeypatch.setattr(imagen_client, "HUGGINGFACE_API_TOKEN", None)

    try:
        imagen_client.generar_imagen("un sensor de humedad")
        assert False, "Debería haber lanzado RuntimeError"
    except RuntimeError as error:
        assert "HUGGINGFACE_API_TOKEN" in str(error)
        print("\n✅ Rechaza correctamente la falta de HUGGINGFACE_API_TOKEN")


def test_generar_imagen_devuelve_bytes_png(monkeypatch):
    monkeypatch.setattr(imagen_client, "HUGGINGFACE_API_TOKEN", "token-de-prueba")

    prompt_capturado = {}

    class ClienteFalso:
        def text_to_image(self, prompt, model):
            prompt_capturado["prompt"] = prompt
            prompt_capturado["modelo"] = model
            return _imagen_pil_de_prueba()

    monkeypatch.setattr(imagen_client, "_obtener_cliente", lambda: ClienteFalso())

    resultado = imagen_client.generar_imagen("diagrama de un bioinsumo inteligente")

    assert isinstance(resultado, bytes)
    imagen_reabierta = Image.open(io.BytesIO(resultado))
    assert imagen_reabierta.format == "PNG"

    assert prompt_capturado["prompt"] == "diagrama de un bioinsumo inteligente"
    assert prompt_capturado["modelo"] == "black-forest-labs/FLUX.1-schnell"

    print("✅ generar_imagen() devuelve bytes PNG válidos, usando el modelo Flux correcto")


if __name__ == "__main__":
    class MonkeypatchSimple:
        def setattr(self, obj, nombre, valor):
            setattr(obj, nombre, valor)

    mp = MonkeypatchSimple()
    test_falta_token_lanza_error(mp)
    test_generar_imagen_devuelve_bytes_png(mp)

    print("\n✅ Todo funciona correctamente")
