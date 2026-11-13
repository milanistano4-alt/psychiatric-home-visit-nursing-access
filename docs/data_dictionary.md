# Data dictionary (`results/`)

## municipality_access.csv (1,884 rows)

| Column | Description |
|---|---|
| municipality_code | 5-digit municipality code (first municipality code of each 500 m grid cell). Tokyo special wards and wards of designated cities are separate units. |
| population_2020 | 2020 population summed over assigned 500 m cells (allocated values, may be fractional) |
| populated_500m_cells | Number of assigned 500 m cells with population > 0 |
| density_per_km2 | population_2020 / (populated_500m_cells × 0.25 km²); an approximation, not official habitable-area density |
| density_quartile | Q1 (lowest) – Q4 (highest); quartiles by number of municipality-equivalents (471 each) |
| e2sfca_relative | Population-weighted mean of the cell-level 30-minute E2SFCA index within the unit, national population-weighted mean = 1 |
| coverage_15min_pct | % of population in cells with at least one registered station within 15 minutes (modelled road travel time) |
| coverage_30min_pct | Same for 30 minutes |

## density_quartile_summary.csv

Per density quartile: number of units, population, density range, population-weighted mean and municipal median of `e2sfca_relative`, and population-weighted 15/30-minute coverage. Values correspond to Tables 2–4 of the manuscript.

## national_summary.json

National indicators of the cell-level 30-minute E2SFCA index (Gini coefficient, population shares below half / above twice the national mean / zero) and counts of stations and grid cells.

## Interpretation

Supply is one unit per registered station; registration does not establish current service provision, staffing or capacity. Population is total population, not the number of people needing psychiatric home-visit nursing. Travel times are modelled motor-vehicle times on OpenStreetMap roads; zero access includes 141 cells (about 658 residents) whose road connection could not be resolved.
