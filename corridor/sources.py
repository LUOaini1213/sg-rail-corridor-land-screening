"""Registry of the open datasets used. All are on data.gov.sg under the Singapore Open Data Licence v1.0.

Keys are used as directory names under data/raw/ and as provenance references in results.
"""
from __future__ import annotations

DATASETS: dict[str, dict] = {
    # Urban Redevelopment Authority (URA), Master Plan 2025 as amended
    "mp25_land_use": {
        "id": "d_7a03324bed531cdff76a16239b0e84e1", "file": "mp25_land_use_amended.geojson",
        "title": "Amendment to Master Plan 2025 Land Use Layer", "publisher": "Urban Redevelopment Authority",
        "use": "Land-use zoning of each Master Plan parcel (LU_DESC); not legal lots",
    },
    "mp25_building": {
        "id": "d_255551acbbce32df735e14d62e067e4f", "file": "mp25_building.geojson",
        "title": "Master Plan 2025 Building Layer", "publisher": "Urban Redevelopment Authority",
        "use": "Indicative building footprints (BLDG_TYPE only; no names)",
    },
    "mp25_rail_line": {
        "id": "d_6615da031916f656152eafa013748d73", "file": "mp25_rail_line_amended.geojson",
        "title": "Amendment to Master Plan 2025 Rail Line Layer", "publisher": "Urban Redevelopment Authority",
        "use": "Check that the illustrative corridor does not follow any rail line shown in the Master Plan",
    },
    "mp25_rail_station": {
        "id": "d_6f5107a8cf6c9a32439cffbfa9013423", "file": "mp25_rail_station_amended.geojson",
        "title": "Amendment to Master Plan 2025 Rail Station Layer", "publisher": "Urban Redevelopment Authority",
        "use": "Outlines of the two existing end stations",
    },
    "mp25_underground": {
        "id": "d_95c0799f265a43b087e9a4ce68d4455a", "file": "mp25_underground_structure.geojson",
        "title": "Master Plan 2025 Underground Structure Layer", "publisher": "Urban Redevelopment Authority",
        "use": "Indicative underground structures near the corridor (flag only)",
    },
    # Singapore Land Authority (SLA)
    "sla_cadastral": {
        "id": "d_e7395d743076a2bcc487b0d12b9bf33b", "file": "sla_cadastral_land_parcel.geojson",
        "title": "SLA Cadastral Land Parcel", "publisher": "Singapore Land Authority",
        "use": "Surveyed land lots (LOT_KEY); the parcel base of the screening",
    },
    "sla_airspace": {
        "id": "d_4522da5e03b0051cd3f5b0f1ab9557e3", "file": "sla_cadastral_airspace_parcel.geojson",
        "title": "SLA Cadastral Airspace Parcel", "publisher": "Singapore Land Authority",
        "use": "Airspace lots over the corridor (flag only)",
    },
    "sla_vacant_state_land": {
        "id": "d_408e0ce796d119ea87b93b2d3402e134", "file": "sla_vacant_state_land.geojson",
        "title": "SLA Vacant State land and properties (GEOJSON)", "publisher": "Singapore Land Authority",
        "use": "State-land indicator (vacant State land managed by SLA); address fields are dropped",
    },
    "sla_managing_agent": {
        "id": "d_df16110220e8fc11717899ad4a463e44", "file": "sla_managing_agent.geojson",
        "title": "SLA Managing Agent (GEOJSON)", "publisher": "Singapore Land Authority",
        "use": "State-land indicator (State land managed by SLA-appointed agents)",
    },
    "sla_state_reserve": {
        "id": "d_0436cc1b096c5da4aa2362f90bcaf935", "file": "sla_state_reserve.geojson",
        "title": "SLA State Reserve (GEOJSON)", "publisher": "Singapore Land Authority",
        "use": "State-reserve indicator",
    },
    # Land Transport Authority (LTA)
    "lta_station_exit": {
        "id": "d_b39d3a0871985372d7e1637193335da5", "file": "lta_mrt_station_exit.geojson",
        "title": "LTA MRT Station Exit (GEOJSON)", "publisher": "Land Transport Authority",
        "use": "Evidence that the two end stations are in operation (they have exits)",
    },
}
