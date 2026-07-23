"""
Prueba el adapter de Europe PMC SIN llamar a internet.
"""

from adapters.europepmc import mapear_a_articulo

# Ejemplo simplificado de un resultado real de Europe PMC, de acceso abierto
item_abierto = {
    "pmid": "36000000",
    "pmcid": "PMC9000000",
    "doi": "10.1111/ejemplo4",
    "title": "Microbioma ruminal y su relación con la producción de metano en bovinos",
    "abstractText": "Se analizó el microbioma ruminal de bovinos bajo distintas dietas para evaluar su efecto en la producción de metano entérico.",
    "journalTitle": "Journal of Dairy Science",
    "firstPublicationDate": "2023-06-01",
    "pubYear": "2023",
    "citedByCount": 5,
    "isOpenAccess": "Y",
    "authorString": "Fernández L, Gómez P, Ríos M.",
}

# Ejemplo cerrado (no open access)
item_cerrado = {
    "pmid": "35000000",
    "title": "Estudio preliminar sobre estrés hídrico en cultivos de maíz",
    "journalTitle": "Crop Science",
    "pubYear": "2021",
    "citedByCount": 2,
    "isOpenAccess": "N",
    "authorString": "Torres A.",
}


def test_mapear_articulo_abierto():
    articulo = mapear_a_articulo(item_abierto)

    assert articulo["fuente"] == "europepmc"
    assert articulo["titulo"].startswith("Microbioma ruminal")
    assert articulo["doi"] == "https://doi.org/10.1111/ejemplo4"
    assert articulo["revista"] == "Journal of Dairy Science"
    assert articulo["anio_publicacion"] == 2023
    assert articulo["tiene_texto_completo"] is True
    assert articulo["autores"] == ["Fernández L", "Gómez P", "Ríos M."]

    print("\nArtículo abierto (Europe PMC):")
    for clave, valor in articulo.items():
        if clave != "metadata_raw":
            print(f"  {clave}: {valor}")


def test_mapear_articulo_cerrado():
    articulo = mapear_a_articulo(item_cerrado)

    assert articulo["tiene_texto_completo"] is False
    assert articulo["doi"] is None
    assert articulo["identificador_externo"] == "35000000"
    assert articulo["url_fuente"] == "https://europepmc.org/abstract/MED/35000000"

    print("\nArtículo cerrado, sin DOI (Europe PMC):")
    for clave, valor in articulo.items():
        if clave != "metadata_raw":
            print(f"  {clave}: {valor}")

    print("\n✅ Todo funciona correctamente")


if __name__ == "__main__":
    test_mapear_articulo_abierto()
    test_mapear_articulo_cerrado()
