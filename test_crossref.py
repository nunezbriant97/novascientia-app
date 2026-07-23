"""
Prueba el adapter de Crossref SIN llamar a internet.
"""

from adapters.crossref import mapear_a_articulo, _armar_fecha, EDITORIALES_VIA_CROSSREF, buscar_por_editorial

# Ejemplo simplificado de un resultado real de Crossref
item_de_ejemplo = {
    "DOI": "10.9999/ejemplo3",
    "title": ["Reducción de emisiones en sistemas ganaderos con manejo rotativo"],
    "container-title": ["Journal of Animal Science"],
    "published": {"date-parts": [[2022, 8, 3]]},
    "is-referenced-by-count": 9,
    "URL": "https://doi.org/10.9999/ejemplo3",
    "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
    "author": [
        {"given": "Lucía", "family": "Fernández"},
        {"given": "Diego", "family": "Ramírez"},
    ],
}

# Ejemplo de revista "cerrada" (sin licencia abierta) -- como Nature/Science
item_cerrado = {
    "DOI": "10.1038/ejemplo-nature",
    "title": ["Nuevo mecanismo de fijación de nitrógeno en arqueas"],
    "container-title": ["Nature"],
    "published": {"date-parts": [[2024]]},  # a veces solo viene el año
    "is-referenced-by-count": 120,
    "URL": "https://doi.org/10.1038/ejemplo-nature",
    "author": [{"given": "Ana", "family": "Torres"}],
}


def test_armar_fecha():
    assert _armar_fecha({"date-parts": [[2023, 5, 10]]}) == "2023-05-10"
    assert _armar_fecha({"date-parts": [[2024]]}) == "2024-01-01"
    assert _armar_fecha(None) is None


def test_mapear_articulo_abierto():
    articulo = mapear_a_articulo(item_de_ejemplo)

    assert articulo["fuente"] == "crossref"
    assert articulo["titulo"] == "Reducción de emisiones en sistemas ganaderos con manejo rotativo"
    assert articulo["doi"] == "https://doi.org/10.9999/ejemplo3"
    assert articulo["revista"] == "Journal of Animal Science"
    assert articulo["anio_publicacion"] == 2022
    assert articulo["tiene_texto_completo"] is True
    assert articulo["autores"] == ["Lucía Fernández", "Diego Ramírez"]

    print("\nArtículo abierto (Crossref):")
    for clave, valor in articulo.items():
        if clave != "metadata_raw":
            print(f"  {clave}: {valor}")


def test_mapear_articulo_cerrado():
    articulo = mapear_a_articulo(item_cerrado)

    assert articulo["revista"] == "Nature"
    # Al no tener licencia declarada, lo marcamos como NO texto completo
    assert articulo["tiene_texto_completo"] is False
    assert articulo["anio_publicacion"] == 2024

    print("\nArtículo cerrado, ej. Nature (Crossref):")
    for clave, valor in articulo.items():
        if clave != "metadata_raw":
            print(f"  {clave}: {valor}")

    print("\n✅ Todo funciona correctamente")


def test_editorial_no_soportada_lanza_error():
    try:
        buscar_por_editorial("microbioma", "nature", limite=5)
        assert False, "Debería haber lanzado ValueError"
    except ValueError as error:
        assert "no soportada" in str(error)
        print("\n✅ Rechaza correctamente editoriales no soportadas:", error)


if __name__ == "__main__":
    test_armar_fecha()
    test_mapear_articulo_abierto()
    test_mapear_articulo_cerrado()
    test_editorial_no_soportada_lanza_error()
