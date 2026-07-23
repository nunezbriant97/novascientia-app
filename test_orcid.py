"""
Prueba el adapter de ORCID SIN llamar a internet.

Ojo: no probamos obtener_token() ni buscar() acá porque requieren
credenciales reales y conexión -- eso lo probás vos en tu máquina
una vez que tengas ORCID_CLIENT_ID y ORCID_CLIENT_SECRET en el .env.
Acá probamos la parte que SÍ podemos verificar sin red: el mapeo.
"""

from adapters.orcid import mapear_a_autor, _extraer_perfil_de_json

# Ejemplo simplificado de cómo luce un perfil real de ORCID
perfil_de_ejemplo = {
    "person": {
        "name": {
            "given-names": {"value": "Brayan"},
            "family-name": {"value": "Nuñez"},
        }
    },
    "activities-summary": {
        "employments": {
            "affiliation-group": [
                {
                    "summaries": [
                        {
                            "employment-summary": {
                                "organization": {
                                    "name": "Universidad Nacional del Nordeste",
                                    "address": {"country": "AR"},
                                }
                            }
                        }
                    ]
                }
            ]
        }
    },
}


def test_mapear_a_autor_basico():
    autor = mapear_a_autor("0000-0002-1825-0097", "Ana", "Torres")

    assert autor["orcid"] == "0000-0002-1825-0097"
    assert autor["nombre_completo"] == "Ana Torres"
    assert autor["institucion"] is None  # la búsqueda básica no trae esto

    print("\nAutor básico (solo búsqueda):")
    print(autor)


def test_extraer_perfil_completo():
    autor = _extraer_perfil_de_json("0000-0001-2345-6789", perfil_de_ejemplo)

    assert autor["orcid"] == "0000-0001-2345-6789"
    assert autor["nombre_completo"] == "Brayan Nuñez"
    assert autor["institucion"] == "Universidad Nacional del Nordeste"
    assert autor["pais"] == "AR"

    print("\nAutor con perfil completo (institución incluida):")
    print(autor)

    print("\n✅ Todo funciona correctamente")


if __name__ == "__main__":
    test_mapear_a_autor_basico()
    test_extraer_perfil_completo()
