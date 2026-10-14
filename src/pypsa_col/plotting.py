"""PyPSA workshop carrier colours (PyPSA Labs / data-science-for-esm).

The notebook at workshop1.pypsalabs.org is a private JupyterLab session. The
palette below is the public workshop mapping used in that course:

    n.add("Carrier", colors.keys(), color=colors.values(), overwrite=True)

See https://open-energy-transition.github.io/data-science-for-esm/09-workshop-pypsa.html
and fneum/data-science-for-esm (``A slightly more realistic example``).
"""

from __future__ import annotations

# Exact names and matplotlib colours from the PyPSA dispatch workshop.
WORKSHOP_COLORS = {
    "Gas": "tomato",
    "Hard Coal": "dimgrey",
    "Run of River": "turquoise",
    "Waste": "olive",
    "Brown Coal": "peru",
    "Oil": "black",
    "Storage Hydro": "teal",
    "Other": "whitesmoke",
    "Multiple": "whitesmoke",
    "Nuclear": "deeppink",
    "Geothermal": "darkorange",
    "Wind Offshore": "lightskyblue",
    "Wind Onshore": "royalblue",
    "Solar": "gold",
    "Pumped Hydro": "lightseagreen",
    "AC": "crimson",
    "load shedding": "red",
}

NICE_NAME = {
    "Gas": "Gas",
    "Hard Coal": "Carbón",
    "Run of River": "Filo de agua",
    "Waste": "Biomasa / cogen.",
    "Brown Coal": "Carbón bajo",
    "Oil": "Diésel / combustibles líquidos",
    "Storage Hydro": "Hidro con embalse",
    "Other": "Otro",
    "Wind Onshore": "Eólica",
    "Solar": "Solar",
    "Pumped Hydro": "Bombeo",
    "load shedding": "Demanda no atendida",
    "AC": "CA",
}

# Plot stacking order (bottom → top), matching typical PyPSA dispatch notebooks.
STACK_ORDER = [
    "Storage Hydro",
    "Run of River",
    "Pumped Hydro",
    "Hard Coal",
    "Brown Coal",
    "Gas",
    "Oil",
    "Waste",
    "Geothermal",
    "Nuclear",
    "Solar",
    "Wind Onshore",
    "Wind Offshore",
    "Other",
    "load shedding",
]
