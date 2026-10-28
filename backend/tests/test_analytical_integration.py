"""End-to-end guarantees for the NetSquid-free physical-rate demo."""
import math
from fastapi.testclient import TestClient
from main import app
from stratoq_demo.setup import default_scenario
from stratoq_demo.models import WeatherRegion, OpticalLinkOverride
from stratoq_demo.physical_setup import create_physical_network
from stratoq_demo.resource_allocator import allocate
from stratoq_demo.real_setup_bridge import to_real_setup_payload
from stratoq_demo.trajectories import TRAJECTORIES


def test_directed_physical_objects_and_arrays():
    s=default_scenario()
    p=create_physical_network(s)
    assert len(p.ground_stations)==2 and len(p.balloons)==1
    assert len(p.links)==4 and len(p.demands)==1
    assert all(len(l.K_MAX)==s.config.slots for l in p.links)
    assert all(len(l.W)==s.config.slots and len(l.V)==s.config.slots for l in p.links)
    assert all(all(k>=0 and math.isfinite(k) for k in l.K_MAX) for l in p.links)
    assert p.links[0].K_MAX[0] > 0
    exported=to_real_setup_payload(s)
    assert len(exported['links'])==4 and 'K_MAX' in exported['links'][0]
    assert exported['links'][0]['K_MAX'][0]==p.links[0].K_MAX[0]


def test_physical_rate_tracks_range_and_configuration():
    s=default_scenario()
    original=allocate(s).frames[0].links[0].capacity_bps
    assert original>0
    s.config.optical.source_rate_hz*=0.5
    assert math.isclose(allocate(s).frames[0].links[0].capacity_bps,original/2,rel_tol=3e-4)
    s.config.optical.source_rate_hz*=2
    s.balloons[0].lat+=0.15
    shifted=allocate(s).frames[0].links[0]
    assert shifted.distance_km > allocate(default_scenario()).frames[0].links[0].distance_km
    assert shifted.capacity_bps < original


def test_weather_loss_is_proportional_and_changes_buffers():
    dry=default_scenario()
    s=dry.model_copy(deep=True)
    hap=s.balloons[0]
    s.weather_regions=[WeatherRegion(id='w1',name='Heavy fog',lat=hap.lat,lon=hap.lon,
                                    effect='fog',radius_km=100,attenuation_db=10)]
    rate_dry=allocate(dry).frames[0].links[0].capacity_bps
    rate_wet=allocate(s).frames[0].links[0].capacity_bps
    assert math.isclose(rate_wet/rate_dry,0.1,rel_tol=1e-3)
    assert allocate(s).frames[0].stored_bits_total <= allocate(dry).frames[0].stored_bits_total


def test_qkp_conservation_uses_kmax_no_random_rate():
    s=default_scenario();s.config.slots=3;s.demands=[]
    p=create_physical_network(s)
    result=allocate(s)
    for lid,rates in p.rate_by_link.items():
        recorded=[next(l for l in fr.links if l.id==lid).capacity_bps for fr in result.frames]
        assert all(abs(x-y)<0.01 for x,y in zip(recorded,rates))
    for fr in result.frames:
        assert fr.stored_bits_total <= sum(g.capacity_bits for g in s.ground_stations)
        assert all(0<=q.fill_fraction<=1 for q in fr.qkps)
    assert result.frames[0].stored_bits_total > 0
    assert result.frames[1].stored_bits_total >= result.frames[0].stored_bits_total


def test_offline_trajectory_and_weather_adapt_to_each_time_slot():
    s=default_scenario();s.config.slots=2;s.config.slot_seconds=60
    h=s.balloons[0]
    TRAJECTORIES['integration-demo']={'times':[0.,60.,120.],
        'lats':[h.lat,h.lat+1,h.lat+1], 'lons':[h.lon,h.lon,h.lon],
        'alts':[15.,15.,15.], 'duration_seconds':120., 'rows':3}
    try:
        h.trajectory_id='integration-demo'
        p=create_physical_network(s)
        assert p.slots==2
        assert p.balloons[0].la==[h.lat,h.lat+1]
        assert p.rate_by_link['gs-1:hap-1'][1] < p.rate_by_link['gs-1:hap-1'][0]
        fr=allocate(s).frames
        assert fr[0].positions[h.id]['lat'] != fr[1].positions[h.id]['lat']
    finally:
        TRAJECTORIES.pop('integration-demo',None)


def test_manual_link_disable_produces_zero_real_kmax():
    s=default_scenario()
    s.link_overrides=[OpticalLinkOverride(source='gs-1',target='hap-1',enabled=False)]
    p=create_physical_network(s)
    assert p.rate_by_link['gs-1:hap-1']==[0]*s.config.slots
    r=allocate(s)
    assert r.frames[0].links[0].capacity_bps==0
    assert r.frames[0].demands[0].served_bps==0


def test_api_reports_analytical_engine():
    c=TestClient(app)
    assert c.get('/api/health').json()['engine']=='balloon-qnet-theoretical'
    response=c.post('/api/simulate',json=default_scenario().model_dump())
    assert response.status_code==200,response.text
    assert response.json()['engine']=='balloon-qnet-theoretical'
