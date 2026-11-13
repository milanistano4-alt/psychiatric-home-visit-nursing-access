# Input data

| Data | Source | Version / date | Used for | Availability |
|---|---|---|---|---|
| Stations registered for psychiatric home-visit nursing (訪問看護基本療養費の精神科訪問看護の届出, "Houkan 10") | Registration lists published by the eight Regional Bureaus of Health and Welfare (地方厚生局) | Reference dates 1 August (10 prefectures, 5,186 records), 1 September (19 prefectures, 7,005 records) or 1 October 2026 (18 prefectures, 4,168 records), depending on the bureau | Supply locations (16,359 stations; 16,345 with coordinates) | Original lists are public on the bureaus' websites. The compiled frame with coordinates (assigned by the Japanese Association of Psychiatric Home-Visit Nursing using address geocoding by the Geospatial Information Authority of Japan) is available from the corresponding author on reasonable request. |
| 500 m grid population | National Land Numerical Information (国土数値情報), 500 m mesh population projections, 2024 edition (Ministry of Land, Infrastructure, Transport and Tourism); 2020 values | 2024 edition | Demand (126.15 million people, about 470,000 cells) | Public download from the National Land Numerical Information website, subject to its terms of use. |
| Road network | OpenStreetMap, Geofabrik regional extracts for Japan (Hokkaido, Tohoku, Kanto, Chubu, Kansai, Chugoku, Shikoku, Kyushu) | Extracts dated 12–15 October 2026 | Travel times | © OpenStreetMap contributors, Open Database License (ODbL). Derived graphs and travel-time matrices are not redistributed here; they can be regenerated with the code. |
| Municipality codes | Municipality code field of the population grid data | As above | Municipality-equivalents (1,884) | Public (as above). |
| Secondary medical areas | Secondary medical areas (2024) and municipality correspondence table | 2024 | Supplementary Table S1 only | Public. |

## Integrity records

Hashes of the regional road graphs, the merged national graph (SHA-256 `5408d489e30834807b64a8e6fe2308bd39b6eeacd8e4bd7a6c86deb843028c44`) and the per-prefecture matrices were recorded during the original run and re-verified in November 2026, when all 47 prefecture analysis matrices were regenerated and matched the stored records.

## What is not included

- No facility names, addresses, telephone numbers or facility-level identifiers.
- No personal data of patients, staff or training participants (none were used).
- No coordinates derived from commercial geocoding services.
