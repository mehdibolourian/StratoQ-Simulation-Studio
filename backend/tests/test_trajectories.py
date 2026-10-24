import io
from fastapi.testclient import TestClient
from main import app
from stratoq_demo.setup import default_scenario
from stratoq_demo.trajectories import parse_trajectory
from stratoq_demo.stratoq_adapter import simulate


def test_csv_interpolation_and_dynamic_geometry():
    client = TestClient(app)
    payload = ('Time_s,Longitude_deg,Latitude_deg,Altitude_m\n'
               '0,279,48.62,15000\n'
               '300,279.6,48.8,16000\n'
               '600,280.0,48.9,16000\n').encode()
    res=client.post('/api/trajectories/upload',files={'file':('track.csv',io.BytesIO(payload),'text/csv')})
    assert res.status_code==200, res.text
    data=res.json()
    assert data['first']['lon']==-81
    scenario=default_scenario().model_dump()
    scenario['balloons'][0]['trajectory_id']=data['trajectory_id']
    scenario['config']['slot_seconds']=300
    res=client.post('/api/simulate',json=scenario)
    assert res.status_code==200, res.text
    frames=res.json()['frames']
    assert len(frames)==3
    assert frames[0]['positions']['hap-1']['lon'] == -81
    assert abs(frames[1]['positions']['hap-1']['lon'] + 80.4)<1e-6
    assert frames[0]['links'][0]['distance_km'] != frames[1]['links'][0]['distance_km']
    assert frames[0]['time_seconds']==0 and frames[2]['time_seconds']==600


def test_invalid_upload():
    client=TestClient(app)
    result=client.post('/api/trajectories/upload',files={'file':('bad.csv',b'time,hello\n1,x','text/csv')})
    assert result.status_code==400
