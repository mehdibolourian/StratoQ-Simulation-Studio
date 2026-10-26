from stratoq_demo.setup import default_scenario, build_links
from stratoq_demo.models import WeatherRegion
from stratoq_demo.real_setup_bridge import to_real_setup_payload
from stratoq_demo.resource_allocator import allocate


def test_weather_hap_enters_region():
    scenario = default_scenario()
    hap = scenario.balloons[0]
    scenario.config.slots = 2
    scenario.weather_regions = [WeatherRegion(id='w', name='Rainstorm', effect='rain',
        lat=hap.lat, lon=hap.lon, radius_km=12, attenuation_db=8)]
    assert build_links(scenario)[0]['weather_flags'] == (0,1,0)
    frame = allocate(scenario).frames[0]
    assert frame.weather_by_hap[hap.id] == {'fog':0,'rain':1,'snow':0}
    scenario.weather_regions[0].lat += 3
    assert build_links(scenario)[0]['weather_flags'] == (0,0,0)
    assert allocate(scenario).frames[0].weather_by_hap[hap.id]['rain'] == 0


def test_setup_bridge_fields_and_directed_pairs():
    scenario=default_scenario();scenario.config.slots=3
    scenario.ground_stations[0].n_rx=3
    payload=to_real_setup_payload(scenario)
    assert payload['ground_stations'][0]['args'][2] == 3
    assert payload['system']['THETA'] == 300
    assert len(payload['haps'][0]['args'][0]) == 3
    assert len(payload['links']) == 4  # 2 GS x 1 HAP x 2 directions
    assert len(payload['links'][0]['W']) == 3
    assert len(payload['links'][0]['W'][0]) == 3


def test_rate_cap_and_disabled_link():
    scenario=default_scenario()
    from stratoq_demo.models import OpticalLinkOverride
    scenario.link_overrides=[OpticalLinkOverride(source='gs-1',target='hap-1',capacity_limit_bps=100)]
    assert allocate(scenario).frames[0].links[0].capacity_bps <= 100
    scenario.link_overrides[0].enabled=False
    assert allocate(scenario).frames[0].links[0].capacity_bps == 0
