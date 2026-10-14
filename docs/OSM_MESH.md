# OSM mesh interactivo (más barras)

Red colombiana con **251 barras** (OpenStreetMap mundial, extracto Colombia),
plantas/demanda XM del tablero `dashboard-sin-nodal`, despacho PyPSA con **KVL**,
y mapas **`n.explore()`** (pydeck) como el workshop de PyPSA Labs.

## Snakemake (DAG completo)

```bash
snakemake -s workflow/Snakefile.osm.smk --cores 2
```

Reglas: `mesh` → `attach` → `solve` → (`explore` ∥ `stats`) → `report` → `all`.
Las 7 reglas se ejecutaron en esta entrega (34 s).

## De dónde sale cada capa

| Capa | Fuente |
|---|---|
| Líneas y subestaciones 220/230/500 kV | OSM vía `colombiacongestionV2` (esquema mundial) |
| Coordenadas de centrales | OSM `centrales_osm.geojson` (297 features) |
| CEN, nombres, combustible, `Gene` | XM + pestañas Generación / explorador de planta |
| Demanda | `DemaReal` × pesos declarados del tablero |
| Colores | workshop (`Gas` tomato, `Hard Coal` dimgrey, `Storage Hydro` teal, `Solar` gold, …) |

Los **19 transformadores** unen barras de distinta tensión **en la misma
subestación OSM**. Son supuestos de ingeniería (x=0.12 pu, 400 MVA), no PARATEC.
Sin ellos había 20 islas; con ellos queda **1 componente de 251 barras**
(se descartan 21 buses residuales).

## Mapas interactivos (API del notebook)

```python
n.explore(bus_size=load / 80, map_style="none")
n.explore(bus_size=capacities / 40)          # MultiIndex bus, carrier → tartas
n.explore(line_color=loading, line_flow=..., line_cmap="plasma",
          line_width=n.lines.s_nom / 400)
```

HTML offline: `results/osm-interactive/explore_{load,capacity,flow}.html`.

También `n.statistics.energy_balance()` y `n.statistics.opex()`.

## Números de esta ventana (1–2 ene 2024)

- 251 buses, 326 líneas, 19 transformadores, 545 plantas XM (66 con match OSM).
- Demanda 378 GWh; no atendida **2,2 GWh (0,6 %)** en bolsillos de red, no un
  déficit nacional de capacidad.
- Óptimo HiGHS, 32 400 primales, KVL activo, 0,65 s.
- LMP medios altos en muchos nodos: el VOLL de esos bolsillos contamina el
  promedio. Leer el mapa de flujos, no el colorbar como precio de bolsa.

Esto **no** es el STN oficial ni 147 barras validadas.
