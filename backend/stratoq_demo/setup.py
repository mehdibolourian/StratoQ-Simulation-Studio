"""Topology/geometry setup: a replaceable stand-in for StratoQ setup().

Uses a local equirectangular approximation, valid for compact regional demos.
No physical-layer / security guarantees are implied by its outputs.
"""
import math
from .models import Scenario


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine great-circle distance, in kilometers."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2)**2
    return r * 2 * math.asin(min(1.0, math.sqrt(a)))


def line_intersects_weather(gs, balloon, weather) -> bool:
    """Illustrative 2D *ground projection* test for a circular weather patch."""
    lat0 = math.radians((gs.lat + balloon.lat + weather.lat) / 3)
    cos_lat = max(0.01, math.cos(lat0))
    x1, y1 = gs.lon * 111.32 * cos_lat, gs.lat * 111.32
    x2, y2 = balloon.lon * 111.32 * cos_lat, balloon.lat * 111.32
    xc, yc = weather.lon * 111.32 * cos_lat, weather.lat * 111.32
    dx, dy = x2 - x1, y2 - y1
    fraction = max(0., min(1., ((xc - x1) * dx + (yc - y1) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(x1 + fraction * dx - xc, y1 + fraction * dy - yc) <= weather.radius_km


def build_links(scenario: Scenario):
    """Return candidate HAP–GS optical links; recomputed after every run."""
    links = []
    overrides = {(o.source, o.target): o.enabled for o in scenario.link_overrides}
    for gs in scenario.ground_stations:
        for balloon in scenario.balloons:
            horizontal_km = distance_km(gs.lat, gs.lon, balloon.lat, balloon.lon)
            slant_km = math.hypot(horizontal_km, balloon.altitude_km)
            elevation_deg = math.degrees(math.atan2(balloon.altitude_km, max(1e-6, horizontal_km)))
            loss_db = sum(w.attenuation_db for w in scenario.weather_regions
                          if line_intersects_weather(gs, balloon, w))
            links.append({"id": f"{gs.id}:{balloon.id}", "source": gs.id,
                          "target": balloon.id, "distance_km": slant_km,
                          "elevation_deg": elevation_deg, "weather_loss_db": loss_db,
                          "in_range": horizontal_km <= balloon.coverage_km,
                          "enabled": overrides.get((gs.id, balloon.id), True)})
    return links


def default_scenario() -> Scenario:
    # Two Ontario GSs, one illustrative 15 km balloon approximately halfway between them.
    return Scenario.model_validate({
        "ground_stations": [
            {"id": "gs-1", "name": "Timmins", "lat": 48.4758, "lon": -81.3305},
            {"id": "gs-2", "name": "Iroquois Falls", "lat": 48.7666, "lon": -80.6826},
        ],
        "balloons": [
            {"id": "hap-1", "name": "Strato-01", "lat": 48.6212,
             "lon": -81.00655, "altitude_km": 15, "coverage_km": 85, "yaw_deg": 18},
        ],
        "demands": [{"id": "d-1", "source": "gs-1", "target": "gs-2", "rate_bps": 9000}],
        "weather_regions": [],
        "config": {"slots": 24, "slot_seconds": 300, "base_rate_bps": 36_000},
    })
