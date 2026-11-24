## What is openly available, and what is not

| Need | What was found | Licence | Used here | Gap |
|---|---|---|---|---|
| Legal land lots (cadastre) | SLA Cadastral Land Parcel: lot key and approximate boundary of every surveyed lot, updated weekly | Singapore Open Data Licence v1.0 | Yes, as the parcel base ({{data_quality.lots.count}} lots touch the study box) | No owner, tenure, title depth, encumbrance or title area; the boundaries are approximate (fact F33). Lot particulars come from a lot search on SLA's website (fact sheet source T2), not from open data |
| Land-use zoning | URA Master Plan 2025 land-use layer, as amended | Singapore Open Data Licence v1.0 | Yes, for the dominant zone of each lot | Indicative (F32); zoning polygons are not lots |
| State land | SLA layers of vacant State land, State land managed by SLA's appointed agents, and State reserves | Singapore Open Data Licence v1.0 | Yes, as a State-land indicator | Partial: only those categories are shown, so for most lots tenure stays unknown |
| Railway protection and safeguarding lines | No open layer. LTA sells railway protection plans lot by lot (fact sheet source T2) | - | No | The protection distances of the fact sheet are applied around the fictional structure instead |
| Existing rail lines and stations | URA Master Plan 2025 rail line and station layers, as amended | Singapore Open Data Licence v1.0 | Yes, for interfaces and for the check that the fictional line follows no line on the Master Plan | Indicative centre lines and outlines; the Master Plan calls its rail notations diagrammatic (F27) |
| Road reserve lines | Not found as open data | - | The Master Plan road zone is used as a stand-in | Road reserve boundaries not available |
| Building footprints | URA Master Plan 2025 building layer: island-wide {{raw_survey.layers.mp_buildings:,}} footprints, of which {{raw_survey.layers.mp_building_types.HDB:,}} are HDB blocks and the rest are typed landmark, higher education or health and medical care; {{data_quality.mp_buildings.count}} lie in the study box | Singapore Open Data Licence v1.0 | Yes, for housing-block counts | Not a complete building layer: other buildings are absent |
| Building footprints | OpenStreetMap: {{data_quality.osm_buildings.count}} footprints in the box | Open Database Licence 1.0 | Yes, for buildings in the footprints | Volunteer-mapped; {{data_quality.building_cross_check.matched_by_osm}} of {{data_quality.building_cross_check.mp_buildings}} URA footprints are matched by an OSM footprint covering at least half of them |
| Ground levels | No open elevation model was found among the sources checked | - | No | Tunnel levels are assumed directly in metres above or below the Singapore Height Datum (SHD) |
| OneMap (SLA) | Its terms of use prohibit storing, distributing or publicly displaying SLA data without permission and require developer registration for applications | - | No | No OneMap data, tiles or API keys are in this repository |
| Statutes | Singapore Statutes Online refused automated access | - | Copies held by FAOLEX were read instead | See the fact sheet |

## How the data are handled

- Raw downloads go to `data/raw/<key>/` (git-ignored) through `scripts/fetch_data.py` (data.gov.sg download
  API, spaced requests with back-off) and `scripts/fetch_osm.py` (one Overpass API query). The manifest
  `data/manifest.json` records the dataset page, the download service, access time, size and SHA-256.
- The committed extract `data/study_area/study_area.gpkg` (built by `scripts/build_study_area.py`) covers the
  study box (SVY21 / EPSG:3414) of {{data_quality.study_area_km2:.2f}} square kilometres. Lots, airspace lots and building
  footprints are kept whole so their areas stay true; the other layers are clipped to the box.
- Only the attributes the screening needs are kept. Names and addresses (SLA managing-agent names, State-land
  asset descriptions, block numbers, street names, postal codes, OSM names and addresses) are dropped before
  anything is written to the repository; station names are kept for the two existing end stations.

## Licences and attribution

- **data.gov.sg.** Contains information from Amendment to Master Plan 2025 Land Use Layer, Master Plan 2025
  Building Layer, Amendment to Master Plan 2025 Rail Line Layer, Amendment to Master Plan 2025 Rail Station
  Layer, Master Plan 2025 Underground Structure Layer, SLA Cadastral Land Parcel, SLA Cadastral Airspace Parcel,
  SLA Vacant State land and properties, SLA Managing Agent, SLA State Reserve and LTA MRT Station Exit, accessed
  on 2026-11-24 from data.gov.sg, which is made available under the terms of the Singapore Open Data Licence
  version 1.0 (`https://data.gov.sg/open-data-licence`). The licence does not allow presenting this use as
  official or endorsed.
- **OpenStreetMap.** Building footprints (c) OpenStreetMap contributors, available under the Open Database
  Licence 1.0 (`https://www.openstreetmap.org/copyright`). The `osm_buildings` layer of the extract and the
  building counts derived from it are under the same licence.
- **Documents cited in the fact sheet** (statutes, LTA, URA, SLA and MinLaw publications) are cited, not
  reproduced; only short quotes are given.

## Quirks noticed in the sources

- {{data_quality.mp_buildings.type_with_stray_spaces}} building records in the box carry a building type with a leading space (" HDB").
- Island-wide, LTA's exit layer and URA's station layer name interchange stations differently ("X" against "X
  INTERCHANGE"): {{raw_survey.corridor_selection.exit_station_names_not_matched}} exit-layer station names had no exact match, which is why
  interchange stations were left out of the station-pair search.
- The SLA managing-agent layer carries company names in its only descriptive field; it was reduced to geometry.
- {{data_quality.lots.overlapping_pairs}} pair of lots in the box overlap, by at most {{data_quality.lots.overlap_max_m2:.2f}} square metres; the lots leave
  {{data_quality.lots.coverage.gap_m2:.2f}} square metres of the box uncovered.
