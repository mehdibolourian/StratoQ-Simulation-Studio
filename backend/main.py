"""ERA5 via Open-Meteo API: uvicorn main:app --port 8000 (one worker)."""
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from stratoq_demo.models import Scenario, SimulationResult
from stratoq_demo.setup import default_scenario
from stratoq_demo.stratoq_adapter import simulate
from stratoq_demo.trajectories import register
from stratoq_demo import jobs, open_meteo_jobs as era5_jobs
from stratoq_demo.era5_weather import register_bytes, get_cube, roi_from_scenario
from pathlib import Path
from pydantic import BaseModel
import sysconfig
import importlib.util

app = FastAPI(title="StratoQ Studio API", version="1.0.5")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "balloon-qnet-theoretical", "version": "1.0.5"}


@app.get("/api/scenario/default", response_model=Scenario)
def get_default_scenario():
    return default_scenario()


@app.get('/api/physics/status')
def physics_status():
    """Discover environment readiness without hiding or substituting physics."""
    lowtran = Path(__file__).parent / 'balloon_qnet' / 'lowtran_piccia'
    native = lowtran / ('lowtran7' + sysconfig.get_config_var('EXT_SUFFIX'))
    try:
        from balloon_qnet import transmittance_simulation
        imported = True
        detail = 'Original numerical UplinkChannel/DownlinkChannel available'
    except Exception as exc:
        imported = False
        detail = f'{type(exc).__name__}: {exc}'
    return {'engine': 'balloon-qnet-theoretical', 'channel_import_ok': imported,
            'native_lowtran_present': native.is_file(),
            'native_lowtran_path': str(native), 'detail': detail,
            'note': 'Missing native LOWTRAN may compile on first run if cmake, gfortran, and f2py are installed.'}


@app.post('/api/simulations', status_code=202)
def start_simulation(scenario: Scenario):
    return jobs.launch(scenario)


@app.get('/api/simulations/{job_id}')
def simulation_progress(job_id: str):
    snapshot = jobs.get(job_id)
    if snapshot is None:
        raise HTTPException(404, 'Job not found; backend may have restarted')
    return snapshot


@app.get('/api/simulations/{job_id}/result', response_model=SimulationResult)
def simulation_result(job_id: str):
    snapshot = jobs.get(job_id)
    if snapshot is None:
        raise HTTPException(404, 'Job not found; backend may have restarted')
    if snapshot['status'] == 'failed':
        raise HTTPException(500, snapshot['error'])
    result = jobs.get_result(job_id)
    if result is None:
        raise HTTPException(409, 'Simulation is still running')
    return result


@app.post("/api/simulate", response_model=SimulationResult)
def run_simulation(scenario: Scenario):
    return simulate(scenario)


@app.post('/api/trajectories/upload')
async def upload_trajectory(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.csv', '.xlsx')):
        raise HTTPException(400, 'Expected CSV or XLSX trajectory')
    data = await file.read()
    if len(data) > 40 * 1024 * 1024:
        raise HTTPException(413, 'Trajectory file exceeds 40 MB')
    try:
        return register(file.filename, data)
    except (ValueError, KeyError, EOFError, OSError) as exc:
        raise HTTPException(400, str(exc))


class ERA5Request(BaseModel):
    date_utc: str
    scenario: Scenario


@app.post('/api/era5/jobs', status_code=202)
@app.post('/api/open-meteo/jobs', status_code=202)
def load_era5_historical(request: ERA5Request):
    try:
        return era5_jobs.launch(request.date_utc,request.scenario)
    except era5_jobs.ERA5BusyError as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, OSError) as exc:
        raise HTTPException(400,str(exc))


@app.get('/api/era5/jobs/{job_id}')
@app.get('/api/open-meteo/jobs/{job_id}')
def era5_job_status(job_id: str):
    info=era5_jobs.status(job_id)
    if info is None:raise HTTPException(404,'ERA5 request not found; backend may have restarted')
    return info


@app.post('/api/era5/upload')
async def upload_era5(date_utc: str = Form(...),file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.nc','.nc4','.zip')):
        raise HTTPException(400,'Upload ERA5 NetCDF (.nc) or a CDS NetCDF ZIP (.zip)')
    contents=await file.read(160*1024*1024+1)
    try:
        return register_bytes(contents,date_utc,file.filename)
    except (ValueError,KeyError,ImportError,OSError,RuntimeError) as exc:
        raise HTTPException(400,str(exc))


@app.get('/api/era5/datasets/{dataset_id}/metadata')
def era5_dataset_metadata(dataset_id: str, date_utc: str):
    """Confirm a saved ERA5 identifier is usable after a server restart.

    The frontend may offer a fresh Open-Meteo retrieval only if this exact
    dataset cannot be restored from the persisted cache. Never return
    synthetic weather or substitute a different file for a missing ID.
    """
    try:
        return get_cube(dataset_id, date_utc).metadata()
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(404, f'Cached ERA5 data unavailable: {exc}')


@app.get('/api/era5/datasets/{dataset_id}/frame')
def era5_frame(dataset_id: str,date_utc: str,slot_seconds: int=300,slot: int=0):
    if slot_seconds<1 or slot_seconds>86400 or slot<0 or slot*slot_seconds>=86400:
        raise HTTPException(400,'ERA5 frame must be within selected UTC day')
    try:
        cube=get_cube(dataset_id,date_utc)
        frame=cube.frame(slot*slot_seconds,slot_seconds)
        return {'dataset':cube.metadata(),'slot':slot,'time_seconds':slot*slot_seconds,
                'regions':cube.regions(frame,limit=75)}
    except (ValueError,KeyError,OSError) as exc:
        raise HTTPException(400,str(exc))
