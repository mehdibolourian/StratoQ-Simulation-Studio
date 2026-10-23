from fastapi.testclient import TestClient
from main import app
from stratoq_demo.setup import default_scenario, build_links
from stratoq_demo.resource_allocator import allocate


def test_default_generates_two_links_and_frames():
    case = default_scenario()
    assert len(build_links(case)) == 2
    result = allocate(case)
    assert len(result.frames) == 24
    assert result.frames[0].demands[0].served_bps > 0
    assert result.frames[-1].stored_bits_total >= 0


def test_weather_decreases_rates():
    dry = default_scenario()
    wet = dry.model_copy(deep=True)
    from stratoq_demo.models import WeatherRegion
    wet.weather_regions = [WeatherRegion(id="w1", name="Cloud", lat=48.6,
                                lon=-81.15, radius_km=100, attenuation_db=8)]
    assert allocate(wet).frames[0].links[0].capacity_bps < allocate(dry).frames[0].links[0].capacity_bps


def test_api_round_trip():
    client = TestClient(app)
    scenario = client.get("/api/scenario/default").json()
    response = client.post("/api/simulate", json=scenario)
    assert response.status_code == 200
    assert len(response.json()["frames"]) == scenario["config"]["slots"]


def test_all_pairs_including_out_of_coverage():
    case = default_scenario()
    case.ground_stations.append(case.ground_stations[0].model_copy(update={"id":"gs-3", "name":"Remote", "lat":55.0}))
    case.balloons.append(case.balloons[0].model_copy(update={"id":"hap-2", "name":"Extra"}))
    links = build_links(case)
    assert len(links) == 6
    assert any(not l['in_range'] for l in links)
    result = allocate(case)
    assert len(result.frames[0].links) == 6
    assert all(l.capacity_bps == 0 for l in result.frames[0].links if not l.in_range)


def test_manual_failure_blocks_route_and_reenable_restores():
    from stratoq_demo.models import OpticalLinkOverride
    case = default_scenario()
    original = allocate(case).frames[0].demands[0].served_bps
    assert original > 0
    case.link_overrides = [OpticalLinkOverride(source='gs-1',target='hap-1',enabled=False)]
    result = allocate(case)
    assert result.frames[0].demands[0].served_bps == 0
    assert result.frames[0].links[0].capacity_bps == 0
    assert not result.frames[0].links[0].enabled
    case.link_overrides.clear()
    assert allocate(case).frames[0].demands[0].served_bps == original
