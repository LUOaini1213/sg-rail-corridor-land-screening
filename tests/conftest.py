import socket
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corridor import config  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests run offline: any attempt to open a network connection fails."""
    def guard(*args, **kwargs):
        raise RuntimeError("network access is blocked in tests")
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


def gdf(rows, crs=config.SVY21):
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)


@pytest.fixture
def grid_study():
    """Four 100 m x 100 m lots in a 2 x 2 grid. West half zoned RESIDENTIAL, east half ROAD.
    Lot L4 (north-east) is covered by an SLA vacant-State-land polygon."""
    lots = gdf([{"LOT_KEY": "L1", "geometry": box(0, 0, 100, 100)},
                {"LOT_KEY": "L2", "geometry": box(100, 0, 200, 100)},
                {"LOT_KEY": "L3", "geometry": box(0, 100, 100, 200)},
                {"LOT_KEY": "L4", "geometry": box(100, 100, 200, 200)}])
    land_use = gdf([{"OBJECTID": 1, "LU_DESC": "RESIDENTIAL", "GPR": None, "geometry": box(0, 0, 100, 200)},
                    {"OBJECTID": 2, "LU_DESC": "ROAD", "GPR": None, "geometry": box(100, 0, 200, 200)}])
    empty = gpd.GeoDataFrame({"OBJECTID": []}, geometry=[], crs=config.SVY21)
    vacant = gdf([{"OBJECTID": 9, "CATEGORY": "PPTY", "geometry": box(100, 100, 200, 200)}])
    return {
        "lots": lots, "land_use": land_use, "state_land_vacant": vacant, "state_land_agent": empty.copy(),
        "state_reserve": empty.copy(),
        "osm_buildings": gdf([{"osm_id": "way/1", "building": "residential", "geometry": box(40, 40, 60, 60)},
                              {"osm_id": "way/2", "building": "roof", "geometry": box(140, 140, 150, 150)}]),
        "mp_buildings": gdf([{"OBJECTID": 5, "BLDG_TYPE": "HDB", "geometry": box(40, 40, 60, 60)}]),
        "rail_lines": gdf([{"OBJECTID": 1, "GRND_LEVEL": "ABOVEGROUND", "RAIL_TYPE": "MRT",
                            "geometry": LineString([(-500, -100), (500, -100)])}]),
        "rail_stations": gpd.GeoDataFrame({"NAME": []}, geometry=[], crs=config.SVY21),
    }
