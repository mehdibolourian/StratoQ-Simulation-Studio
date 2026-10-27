"""Regression tests for the v0.6.2 weather UI/backend mismatch."""
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from main import app
from stratoq_demo.models import WeatherRegion
from stratoq_demo.setup import balloon_weather, build_links, default_scenario


@pytest.mark.parametrize('effect,flags', [
    ('fog', (1, 0, 0)), ('rain', (0, 1, 0)), ('snow', (0, 0, 1)),
])
def test_weather_model_and_simulation_roundtrip(effect, flags):
    scenario = default_scenario()
    scenario.config.slots = 2
    hap = scenario.balloons[0]
    scenario.weather_regions = [WeatherRegion(
        id='weather-1', name='Storm', lat=hap.lat, lon=hap.lon,
        radius_km=20, attenuation_db=7, effect=effect)]
    assert build_links(scenario)[0]['weather_flags'] == flags
    assert getattr(scenario.weather_regions[0], 'effect') == effect
    client = TestClient(app)
    response = client.post('/api/simulate', json=scenario.model_dump())
    assert response.status_code == 200, response.text
    frame = response.json()['frames'][0]
    assert tuple(frame['links'][0]['weather_flags']) == flags
    assert frame['weather_by_hap'][hap.id][effect] == 1


def test_legacy_weather_without_effect_field_is_safe():
    scenario = default_scenario()
    hap = scenario.balloons[0]
    scenario.weather_regions = [SimpleNamespace(
        id='weather-old', name='Old fog', lat=hap.lat, lon=hap.lon,
        radius_km=20, attenuation_db=4)]
    assert build_links(scenario)[0]['weather_flags'] == (1, 0, 0)
    assert balloon_weather(hap, scenario)['fog'] == 1


def test_legacy_effect_aliases_and_default():
    common = dict(id='weather-1', name='Weather', lat=48, lon=-81)
    assert WeatherRegion.model_validate({**common, 'type':'cloud'}).effect == 'fog'
    assert WeatherRegion.model_validate({**common, 'weather_type':'rain'}).effect == 'rain'
    assert WeatherRegion.model_validate(common).effect == 'fog'


def test_weather_reduces_demo_link_rate():
    client=TestClient(app)
    scenario=default_scenario()
    scenario.config.slots=2
    payload=scenario.model_dump()
    original=client.post('/api/simulate',json=payload).json()['frames'][0]['links'][0]['capacity_bps']
    hap=scenario.balloons[0]
    payload['weather_regions']=[dict(id='weather-test',name='Rain',lat=hap.lat,lon=hap.lon,
        radius_km=30, attenuation_db=10, effect='rain')]
    changed=client.post('/api/simulate',json=payload).json()['frames'][0]['links'][0]['capacity_bps']
    assert 0 < changed < original


def test_api_build_number():
    response=TestClient(app).get('/api/health')
    assert response.status_code == 200
    assert response.json()['version']=='0.9.0'
