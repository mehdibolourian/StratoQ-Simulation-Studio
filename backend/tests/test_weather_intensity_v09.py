"""Physical-rate sensitivity to weather intensity, legacy schema, and layer overlap."""
from stratoq_demo.models import WeatherRegion
from stratoq_demo.setup import build_links, default_scenario
from stratoq_demo.weather_physics import regional_weather_loss_db


def effect_region(effect, **kw):
    return WeatherRegion(id='weather-intensity', name='Weather', lat=48.62, lon=-81.0,
                         effect=effect, radius_km=100, attenuation_db=0, **kw)


def test_fog_visibility_controls_loss():
    s=default_scenario()
    s.weather_regions=[effect_region('fog', visibility_km=0.2)]
    heavy=build_links(s)[0]['weather_loss_db']
    s.weather_regions=[effect_region('fog', visibility_km=5)]
    light=build_links(s)[0]['weather_loss_db']
    assert heavy > light > 0


def test_rain_and_snow_rate_controls_loss():
    s=default_scenario()
    for effect in ('rain','snow'):
        s.weather_regions=[effect_region(effect, precipitation_rate_mm_h=0)]
        assert build_links(s)[0]['weather_loss_db']==0
        s.weather_regions=[effect_region(effect, precipitation_rate_mm_h=2)]
        low=build_links(s)[0]['weather_loss_db']
        s.weather_regions=[effect_region(effect, precipitation_rate_mm_h=20)]
        high=build_links(s)[0]['weather_loss_db']
        assert high>low>0


def test_region_not_on_link_has_zero_loss():
    s=default_scenario()
    s.weather_regions=[WeatherRegion(id='far', name='Far',lat=45,lon=-75,
                                     effect='rain',radius_km=3,precipitation_rate_mm_h=50)]
    assert all(link['weather_loss_db']==0 for link in build_links(s))


def test_backward_compatible_fixed_loss():
    s=default_scenario()
    s.weather_regions=[WeatherRegion(
        id='old',name='Old',lat=48.62,lon=-81,radius_km=100,effect='fog',attenuation_db=4)]
    assert abs(build_links(s)[0]['weather_loss_db']-4)<1e-10


def test_layer_height_restricts_weather_effect():
    s=default_scenario()
    g=s.ground_stations[0];h=s.balloons[0]
    w=effect_region('fog',visibility_km=0.5)
    assert regional_weather_loss_db(g,h,w)>0
    # Weather around HAP at very high altitude but not lower portion of path.
    w.lat=h.lat;w.lon=h.lon;w.radius_km=0.5
    assert regional_weather_loss_db(g,h,w)==0
