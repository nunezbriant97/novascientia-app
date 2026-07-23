"""
Prueba el adapter de Semantic Scholar SIN llamar a internet,
igual que hicimos con test_openalex.py.
"""

from adapters.semantic_scholar import mapear_a_articulo

# Ejemplo simplificado de cómo luce un resultado real de Semantic Scholar
item_de_ejemplo = {
    "paperId": "abc123def456",
    "title": "Efecto de biofertilizantes en el rendimiento de soja",
    "abstract": "Este estudio evalúa el efecto de biofertilizantes sobre el rendimiento de cultivos de soja bajo estrés hídrico.",
    "year": 2024,
    "publicationDate": "2024-03-15",
    "venue": "Agronomy Journal",
    "citationCount": 17,
    "externalIds": {"DOI": "10.5678/ejemplo2"},
    "openAccessPdf": {"url": "https://example.org/paper456.pdf", "license": "cc-by"},
    "authors": [
        {"name": "María López"},
        {"name": "Carlos Sosa"},
    ],
}


def test_mapear_a_articulo():
    articulo = mapear_a_articulo(item_de_ejemplo)

    assert articulo["fuente"] == "semantic_scholar"
    assert articulo["titulo"] == "Efecto de biofertilizantes en el rendimiento de soja"
    assert articulo["resumen"].startswith("Este estudio evalúa")
    assert articulo["doi"] == "https://doi.org/10.5678/ejemplo2"
    assert articulo["anio_publicacion"] == 2024
    assert articulo["revista"] == "Agronomy Journal"
    assert articulo["tiene_texto_completo"] is True
    assert articulo["citas_count"] == 17
    assert articulo["autores"] == ["María López", "Carlos Sosa"]
    assert articulo["metadata_raw"] is not None

    print("\nArtículo normalizado (Semantic Scholar):")
    for clave, valor in articulo.items():
        if clave != "metadata_raw":
            print(f"  {clave}: {valor}")

    print("\n✅ Todo funciona correctamente")


if __name__ == "__main__":
    test_mapear_a_articulo()
