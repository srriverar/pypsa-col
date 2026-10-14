# Ejemplo dashboard-sin-nodal × PyPSA

Nuevo corrido `dashboard-sin`: toma las pestañas **⚡ Generación**, **📈 Demanda** y el
**Explorador de planta** de
[dashboard-sin-nodal](https://dashboard-sin-nodal.streamlit.app/)
y las resuelve con PyPSA, usando la paleta del workshop de PyPSA Labs.

## Qué se tomó de la app (y qué no)

| De la app | En PyPSA-col |
|---|---|
| `ListadoRecursos` → `dim_plantas` (`Type`, `EnerSource`, `RecType`) | `src/pypsa_col/dashboard_sin.py` |
| Mix y perfiles por planta (`Gene/Recurso`) | `resources/dashboard-sin/explorador_planta.csv` |
| `DemaReal` nacional, sin filtrar por planta | `demanda_zonal_mw.csv` |
| 7 subregiones declaradas + `PESO_DEMANDA_NODAL` | buses GUJ/CAR/NOR/CEN/OCC/SUR/ORI |
| Toponimia del nombre de planta | cobertura reportada (~80 % del CEN en este sample) |
| Corredores NTC del tablero | Links bidireccionales sin KVL |
| OPF dual-ascent, GARCH, Q-learning | **No**. Se usa `n.optimize` HiGHS |
| Coordenadas oficiales XM | **No existen** en la API abierta; no se inventan |

El notebook del workshop
(`workshop1.pypsalabs.org/.../02-pypsa-dispatch-problems.ipynb`) vive en un
JupyterLab privado. Los colores se toman del curso público equivalente
(`n.add("Carrier", colors.keys(), color=colors.values())`):

```
Gas tomato · Hard Coal dimgrey · Oil black · Storage Hydro teal ·
Run of River turquoise · Solar gold · Wind Onshore royalblue ·
Waste olive · AC crimson · load shedding red
```

## Cómo correrlo

```bash
python scripts/run_dashboard_sin.py
```

Usa el bundle XM ya descargado (1–2 ene 2024). Informe:
`results/dashboard-sin/informe.html`.

## Lectura del óptimo (esta ventana)

Hidro y renovables se limitan al perfil **observado** (`Gene/Recurso` / CEN).
Las térmicas pueden despachar hasta su CEN. El LP es entonces un despacho
económico del parque térmico dada el agua/sol/viento ya medidos — el ejercicio
clásico de un notebook PyPSA de *dispatch*.

En el sample, el modelo cubre la DemaReal nacional **sin racionamiento**
(el ejemplo `xm-example` anterior racionaba ~49 % porque usaba una flota de
juguete). El óptimo sustituye parte del gas observado por carbón, que en la
función de costo ilustrativa es más barato. Eso no es una predicción de
mérito real del MEM.
