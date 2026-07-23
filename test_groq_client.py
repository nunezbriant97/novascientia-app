"""
Prueba groq_client.py SIN llamar a la API real de Groq (para eso hace
falta GROQ_API_KEY real). Simulamos la respuesta HTTP para verificar
que armamos bien los mensajes y que parseamos bien el JSON de vuelta.
"""

import json

import groq_client


class RespuestaFalsa:
    """Simula lo que devuelve requests.post(...).json() y .raise_for_status()"""

    def __init__(self, contenido: str):
        self._contenido = contenido

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._contenido}}]}


def test_falta_api_key_lanza_error(monkeypatch):
    monkeypatch.setattr(groq_client, "GROQ_API_KEY", None)

    try:
        groq_client.chat("hola")
        assert False, "Debería haber lanzado RuntimeError"
    except RuntimeError as error:
        assert "GROQ_API_KEY" in str(error)
        print("\n✅ Rechaza correctamente la falta de GROQ_API_KEY")


def test_chat_arma_bien_los_mensajes(monkeypatch):
    monkeypatch.setattr(groq_client, "GROQ_API_KEY", "clave-de-prueba")

    mensajes_capturados = {}

    def post_falso(url, json, headers, timeout):
        mensajes_capturados["mensajes"] = json["messages"]
        mensajes_capturados["modelo"] = json["model"]
        return RespuestaFalsa("Hola, soy el Núcleo IA de NovaScientia.")

    monkeypatch.setattr(groq_client.requests, "post", post_falso)

    respuesta = groq_client.chat("¿Qué es un biofertilizante?")

    assert respuesta == "Hola, soy el Núcleo IA de NovaScientia."
    assert mensajes_capturados["modelo"] == "llama-3.3-70b-versatile"
    assert mensajes_capturados["mensajes"][0]["role"] == "system"
    assert "Núcleo IA" in mensajes_capturados["mensajes"][0]["content"]
    assert mensajes_capturados["mensajes"][-1]["content"] == "¿Qué es un biofertilizante?"

    print("✅ chat() arma correctamente el system prompt y usa el modelo Llama")


def test_generar_hipotesis_parsea_json(monkeypatch):
    monkeypatch.setattr(groq_client, "GROQ_API_KEY", "clave-de-prueba")

    json_de_ejemplo = json.dumps({
        "decision_final": "descartada",
        "motivo_descarte": "Ya existe una patente equivalente",
        "novedad": {
            "nivel": "baja",
            "existe_idea_igual": False,
            "existe_combinacion_equivalente": True,
            "existe_tecnologia_comercial": False,
            "existe_patente_relacionada": True,
        },
        "combinacion": {"descubrimientos": [], "es_trivial": True, "nueva_funcion": ""},
        "impacto": {"categorias_cumplidas": [], "cumple_al_menos_uno": False},
        "prioridad_agricola": {"area": None, "subtema": None},
        "hipotesis": {
            "titulo_cientifico": None,
            "idea_central": None,
            "diferencia_estado_actual": None,
            "antecedentes": {"patentes_similares": [], "articulos_relacionados": []},
            "riesgos": [],
            "experimentos_sugeridos": [],
        },
    })

    modelo_capturado = {}

    def post_falso(url, json, headers, timeout):
        modelo_capturado["modelo"] = json["model"]
        modelo_capturado["forzo_json"] = "response_format" in json
        return RespuestaFalsa(json_de_ejemplo)

    monkeypatch.setattr(groq_client.requests, "post", post_falso)

    resultado = groq_client.generar_hipotesis("Evidencia de prueba sobre biofertilizantes")

    assert isinstance(resultado, dict)
    assert resultado["decision_final"] == "descartada"
    assert resultado["motivo_descarte"] == "Ya existe una patente equivalente"
    assert modelo_capturado["modelo"] == "deepseek-r1-distill-llama-70b"
    assert modelo_capturado["forzo_json"] is True

    print("✅ generar_hipotesis() usa DeepSeek, fuerza JSON, y parsea bien la respuesta")


if __name__ == "__main__":
    class MonkeypatchSimple:
        def setattr(self, obj, nombre, valor):
            setattr(obj, nombre, valor)

    mp = MonkeypatchSimple()
    test_falta_api_key_lanza_error(mp)
    test_chat_arma_bien_los_mensajes(mp)
    test_generar_hipotesis_parsea_json(mp)

    print("\n✅ Todo funciona correctamente")
