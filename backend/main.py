"""Development API: uvicorn main:app --reload --port 8000"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from stratoq_demo.models import Scenario, SimulationResult
from stratoq_demo.setup import default_scenario
from stratoq_demo.stratoq_adapter import simulate
from stratoq_demo.trajectories import register
from stratoq_demo import jobs
from pathlib import Path
import sysconfig
import importlib.util

app = FastAPI(title="StratoQ Studio API", version="0.9.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "balloon-qnet-theoretical", "version": "0.9.0"}


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
