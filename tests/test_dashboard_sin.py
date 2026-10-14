from pypsa_col.dashboard_sin import PESO_DEMANDA, carrier_of, dim_plantas, zona_por_nombre
from pypsa_col.plotting import WORKSHOP_COLORS
import pandas as pd


def test_demand_shares_sum_to_one():
    assert abs(sum(PESO_DEMANDA.values()) - 1.0) < 1e-9


def test_workshop_palette_has_dispatch_carriers():
    for name in ("Solar", "Wind Onshore", "Storage Hydro", "Gas", "Hard Coal", "Oil"):
        assert name in WORKSHOP_COLORS


def test_carrier_mapping_matches_xm_catalog_fields():
    row = pd.Series(
        {"Tecnologia": "HIDRAULICA", "Tipo_Recurso": "FILO DE AGUA", "Fuente_Energia": "AGUA"}
    )
    assert carrier_of(row) == "Run of River"
    row = pd.Series({"Tecnologia": "SOLAR", "Tipo_Recurso": "NORMAL", "Fuente_Energia": "RAD SOLAR"})
    assert carrier_of(row) == "Solar"
    row = pd.Series({"Tecnologia": "TERMICA", "Tipo_Recurso": "NORMAL", "Fuente_Energia": "CARBON"})
    assert carrier_of(row) == "Hard Coal"


def test_toponymy_hits_known_plants():
    assert zona_por_nombre("PARQUE EOLICO GUAJIRA I") == "GUJ"
    assert zona_por_nombre("CHIVOR") == "CEN"
    assert zona_por_nombre("una planta sin pista") is None


def test_dim_plantas_from_listado_schema():
    raw = pd.DataFrame(
        [
            {
                "Code": "AAA",
                "Name": "CHIVOR",
                "Type": "HIDRAULICA",
                "EnerSource": "AGUA",
                "RecType": "NORMAL",
                "CompanyCode": "X",
                "Disp": "DESPACHADO CENTRALMENTE",
                "State": "OPERACION",
            }
        ]
    )
    dim = dim_plantas(raw)
    assert dim.loc[0, "carrier"] == "Storage Hydro"
    assert dim.loc[0, "zona_toponimia"] == "CEN"
