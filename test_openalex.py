"""
Prueba el adapter de OpenAlex SIN llamar a internet.
Usamos un resultado "de mentira" con la misma forma que devuelve la API real,
para verificar que nuestra función mapear_a_articulo() lo traduce bien.
"""

from adapters.openalex import mapear_a_articulo, reconstruir_resumen

# Este es un ejemplo simplificado de cómo luce UN resultado real de OpenAlex
item_de_ejemplo = {
    "id": "https://openalex.org/W2755950973",
    "doi": "https://doi.org/10.1234/ejemplo",
    "title": "Microbioma del suelo y su efecto en la resistencia a sequía",
    "publication_year": 2023,
    "publication_date": "2023-05-10",
    "cited_by_count": 42,
    "abstract_inverted_index": {
        "El": [0],
        "microbioma": [1],
        "del": [2],
        "suelo": [3],
        "mejora": [4],
        "la": [5],
        "resistencia": [6],
    },
    "primary_location": {
        "source": {"display_name": "Journal of Soil Science"},
        "landing_page_url": "https://example.org/paper123",
        "license": "cc-by",
    },
    "open_access": {"is_oa": True, "oa_url": "https://example.org/paper123.pdf"},
    "authorships": [
        {"author": {"display_name": "Juan Pérez"}},
        {"author": {"display_name": "Ana Gómez"}},
    ],
}


def test_reconstruir_resumen():
    resultado = reconstruir_resumen(item_de_ejemplo["abstract_inverted_index"])
    print("Resumen reconstruido:", resultado)
    assert resultado == "El microbioma del suelo mejora la resistencia"


def test_mapear_a_articulo():
    articulo = mapear_a_articulo(item_de_ejemplo)

    assert articulo["fuente"] == "openalex"
    assert articulo["titulo"] == "Microbioma del suelo y su efecto en la resistencia a sequía"
    assert articulo["anio_publicacion"] == 2023
    assert articulo["revista"] == "Journal of Soil Science"
    assert articulo["tiene_texto_completo"] is True
    assert articulo["citas_count"] == 42
    assert articulo["autores"] == ["Juan Pérez", "Ana Gómez"]
    assert articulo["metadata_raw"] is not None

    print("\nArtículo normalizado:")
    for clave, valor in articulo.items():
        if clave != "metadata_raw":
            print(f"  {clave}: {valor}")

    print("\n✅ Todo funciona correctamente")


if __name__ == "__main__":
    test_reconstruir_resumen()
    test_mapear_a_articulo()
