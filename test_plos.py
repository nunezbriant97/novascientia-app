"""
Prueba el adapter de PLOS SIN llamar a internet.
"""

from adapters.plos import mapear_a_articulo

# Ejemplo simplificado de un resultado real de PLOS
item_de_ejemplo = {
    "id": "10.1371/journal.pone.0123456",
    "title_display": "Impacto de la agricultura regenerativa en la retención de carbono del suelo",
    "abstract": [
        "Este estudio evaluó el impacto de prácticas de agricultura regenerativa sobre el carbono orgánico del suelo en distintos tipos de cultivo."
    ],
    "journal": "PLOS ONE",
    "publication_date": "2023-09-12T00:00:00Z",
    "author_display": ["Gómez, Laura", "Pereyra, Martín"],
    "counter_total_all": 542,
}


def test_mapear_a_articulo():
    articulo = mapear_a_articulo(item_de_ejemplo)

    assert articulo["fuente"] == "plos"
    assert articulo["doi"] == "https://doi.org/10.1371/journal.pone.0123456"
    assert articulo["titulo"].startswith("Impacto de la agricultura regenerativa")
    assert articulo["resumen"].startswith("Este estudio evaluó")
    assert articulo["revista"] == "PLOS ONE"
    assert articulo["anio_publicacion"] == 2023
    assert articulo["tiene_texto_completo"] is True  # PLOS siempre es open access
    assert articulo["licencia"] == "cc-by"
    assert articulo["autores"] == ["Gómez, Laura", "Pereyra, Martín"]
    assert articulo["metadata_raw"] is not None

    print("\nArtículo normalizado (PLOS):")
    for clave, valor in articulo.items():
        if clave != "metadata_raw":
            print(f"  {clave}: {valor}")

    print("\n✅ Todo funciona correctamente")


if __name__ == "__main__":
    test_mapear_a_articulo()
