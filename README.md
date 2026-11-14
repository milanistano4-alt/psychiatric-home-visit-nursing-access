# Spatial access to psychiatric home-visit nursing stations in Japan

Code and aggregated results for the nationwide cross-sectional study of geographic access to stations registered for psychiatric home-visit nursing in Japan, using the enhanced two-step floating catchment area (E2SFCA) method.

> Manuscript under review. Citation details will be added on publication.
>
> Authors: Yoshiyuki Takashima, Takemasa Ishikawa, Ryo Horiike

## Contents

```
.
├── README.md
├── LICENSE                     MIT (code). Results: CC BY 4.0 (see below)
├── CITATION.cff
├── requirements.txt            Python package versions used for the reproduction run
├── docs/
│   ├── data_sources.md         Input data, where to obtain them, and licences
│   └── data_dictionary.md      Column definitions for the files in results/
├── results/                    Aggregated outputs (no facility-level data)
│   ├── national_summary.json
│   ├── density_quartile_summary.csv
│   └── municipality_access.csv
└── code/
    ├── data_acquisition/       Population data download and audit helpers
    ├── pipeline/               Road graph, travel-time matrix and matrix-derivation modules
    └── workflow/               Run scripts for each step (with input hash checks)
```

## Pipeline

Travel times are directed shortest paths (Dijkstra) on an OpenStreetMap drivable road network. Road-segment speeds are capped at 40 km/h and multiplied by 0.9 (maximum 36 km/h). Each station is placed at the centroid of its 500 m grid cell and residents at populated-cell centroids; centroids are connected to the nearest eligible road node (excluding nodes on limited-access roads only) by a straight-line connector timed at 15 km/h, and connections longer than 1 km are treated as unresolved. Matrices store all origin–cell pairs within 60 minutes.

| Step | Script(s) | Output |
|---|---|---|
| 1. Regional road graphs from OSM extracts | `code/pipeline/build_reviewed_road_graph.py`, `run_R022_national_graph_build.py` | 8 regional graphs (`.npz` + metadata) |
| 2. Merge into a national graph | `code/pipeline/merge_reviewed_road_graphs.py` (`code/workflow/rebuild_national_graph_guarded.py` runs it with hash checks) | national graph |
| 3. Population input | `code/pipeline/build_R021_population_input.py` (helpers in `code/data_acquisition/`) | 500 m population grid (2020) |
| 4. Travel-time matrices per prefecture | `code/pipeline/R023_runtime/traveltime_national_graph.py` with `pilot_config.py`, `graph_integrity.py`; memory adapter in `R032_memory_runtime/` | origin-to-cell travel times (≤60 min) |
| 5. Added/relocated stations (delta origins) | `code/pipeline/R052_delta_worker.py`, `R052_delta_primitives.py`, `R037_mapped_numeric.py`, `run_R052_delta_controller.py` | delta matrices |
| 6. Analysis matrices (parent subset + delta) | `code/pipeline/R322_A1_runtime_v2/R054_derive_worker.py`, `R054_frame_layout.py`; batch: `code/workflow/rederive_all47_matrices_guarded.py` | 47 prefecture matrices |
| 7. National E2SFCA (30 min) | `code/workflow/national_e2sfca.py` | national cell-level index and summary |
| 8. Municipality density quartiles | `code/workflow/municipality_density_quartiles.py`, check: `density_quartile_check.py` | `results/` |
| 9. Rank correlations | `code/workflow/rank_correlations.py` | Spearman / partial correlations |

`code/workflow/rebuild_three_prefectures_guarded.py` regenerates the Kanagawa, Osaka and Nara matrices; `check_origin_station_alignment.py` checks origin–station alignment.

### E2SFCA specification

- Catchment: 30 minutes. Decay: truncated Gaussian, w(t) = [exp(−0.5(t/30)²) − exp(−0.5)] / [1 − exp(−0.5)] for t ≤ 30, 0 otherwise.
- Supply: one unit per registered station (equal facility-equivalents).
- Demand: total 2020 population of 500 m grid cells.
- Index normalised so that the population-weighted national mean is 1.
- Municipality-equivalents: first municipality code of each grid cell (Tokyo special wards and wards of designated cities treated separately), 1,884 units; density = population / (populated cells × 0.25 km²); quartiles by number of units (471 each).

### Status of the code

The scripts are published as used. Internally they reference the original project folder layout, in which `code/pipeline/` was `research/codex/`, `code/workflow/` was `research/handoff/` and `code/data_acquisition/` was `research/PHVN-20261024/scripts/`; working-folder names that appear inside the scripts (e.g. `R322_...`) are internal job identifiers. They also reference the input files described in `docs/data_sources.md`, and several scripts verify input hashes before running. They are not packaged as a one-command workflow. Full reproduction of steps 1–6 requires about 50 GB of free disk and 16 GB of memory (the national graph merge peaked at about 9 GB).

Python 3.12; package versions in `requirements.txt`.

### Changes made for publication

The file contents are byte-identical to the versions used in the analysis (SHA-256 values in `CHECKSUMS.sha256`). From v1.0.1, folders and the run scripts in `code/workflow/` were renamed to descriptive English names without changing their contents. One edit was made: in `code/pipeline/run_R022_national_graph_build.py` a local scratch directory path containing a user name was replaced with `scratch/R022_indices`. Some helper modules (`graph_integrity.py`, `artifact_hash.py`) are included in more than one folder because the scripts import them from their own directory.

## Data availability

- **Results in `results/`** are aggregated to municipality-equivalents or the nation and contain no facility-level data.
- **Station registry and station coordinates** (16,359 stations registered for psychiatric home-visit nursing with Regional Bureaus of Health and Welfare, reference dates 1 August, 1 September and 1 October 2026; coordinates assigned by the Japanese Association of Psychiatric Home-Visit Nursing) are **available from the corresponding author on reasonable request**. The underlying registers are published by each Regional Bureau of Health and Welfare.
- **Population and road data** are publicly available (see `docs/data_sources.md`). Travel-time matrices derived from OpenStreetMap are not redistributed because of their size; they can be regenerated with the code.

## Licence

- Code: MIT License (`LICENSE`).
- Aggregated results in `results/`: Creative Commons Attribution 4.0 International (CC BY 4.0).
- Road network derived from © OpenStreetMap contributors, available under the Open Database License (ODbL).
- Population data: National Land Numerical Information (Ministry of Land, Infrastructure, Transport and Tourism), see `docs/data_sources.md`.

## Contact

Yoshiyuki Takashima, Nara Medical University (corresponding author). Contact details are given in the published article.
