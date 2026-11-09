"""ERA5 via Open-Meteo API: uvicorn main:app --port 8000 (one worker)."""
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from stratoq_demo.models import Scenario, SimulationResult
from pathlib import Path
import json
from stratoq_demo.setup import default_scenario
from stratoq_demo.stratoq_adapter import simulate
from stratoq_demo.trajectories import register
from stratoq_demo import jobs, open_meteo_jobs as era5_jobs
from stratoq_demo.era5_weather import register_bytes, get_cube, roi_from_scenario
from stratoq_demo import learning_jobs
from stratoq_demo.learning_presets import PRESET, preset_metadata, validate_learning_scenario, validate_time_grid
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


@app.get('/api/experiments/builtin')
def builtin_experiments():
    data = json.loads((Path(__file__).resolve().parent / 'stratoq_demo' / 'builtin_experiments.json').read_text())
    return {'version': data['version'], 'notes': data['notes'],
            'experiments': [{k:v for k,v in preset.items() if k!='scenario'} for preset in data['experiments']]}

@app.get('/api/experiments/builtin/{preset_id}')
def builtin_experiment(preset_id: str):
    data = json.loads((Path(__file__).resolve().parent / 'stratoq_demo' / 'builtin_experiments.json').read_text())
    for preset in data['experiments']:
        if preset['id'] == preset_id:
            return {**{k:v for k,v in preset.items() if k!='scenario'},
                    'scenario': Scenario.model_validate(preset['scenario']).model_dump(mode='json')}
    raise HTTPException(404, 'Unknown built-in experiment')

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


# ---------------------------------------------------------------------------
# Learning Lab: isolated genuine PPO jobs; independent of existing simulations.
# ---------------------------------------------------------------------------
class LearningStart(BaseModel):
    preset: str = PRESET
    scenario: dict | None = None  # Complete fixed network: immutable snapshot per job.
    slots: int = 24
    slot_seconds: int = 300
    episodes: int = 30
    checkpoint_every: int = 5
    seed: int = 42
    learning_rate: float = 1e-4
    gamma: float = .99
    gae_lambda: float = .95
    clip: float = .2
    ppo_epochs: int = 5
    batch_size: int = 64
    entropy_start: float = .01
    entropy_end: float = .001
    compare_baselines: bool = False
    curriculum_enabled: bool = True
    curriculum_first_demands: int = 1
    curriculum_second_demands: int = 2
    curriculum_first_end_pct: int = 33
    curriculum_second_end_pct: int = 67


@app.get('/api/learning/preset')
def learning_preset(slots: int = 24, slot_seconds: int = 300):
    try:
        return preset_metadata(slots, slot_seconds)
    except ValueError as exc:
        raise HTTPException(400,str(exc))


@app.get('/api/learning/latest')
def latest_learning_run():
    return learning_jobs.latest()


@app.post('/api/learning/runs',status_code=202)
def create_learning_run(request: LearningStart):
    if request.preset != PRESET:
        raise HTTPException(400,'Unknown Learning Lab preset')
    try:
        validate_time_grid(request.slots, request.slot_seconds)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    if request.episodes < 1:
        raise HTTPException(400,'Episodes must be a positive integer')
    if request.checkpoint_every < 1:
        raise HTTPException(400,'Checkpoint interval must be a positive integer')
    if not 0 <= request.seed < 2**31:
        raise HTTPException(400,'Seed must be a nonnegative 31-bit integer')
    if not 1e-7 <= request.learning_rate <= 0.01:
        raise HTTPException(400,'Learning rate must be in [1e-7, 0.01]')
    if not 0 <= request.gamma <= 1 or not 0 <= request.gae_lambda <= 1:
        raise HTTPException(400,'Gamma and GAE lambda must be in [0,1]')
    if not .01 <= request.clip <= .5:
        raise HTTPException(400,'PPO clipping must be in [0.01,0.5]')
    if not 1 <= request.ppo_epochs <= 30 or not 1 <= request.batch_size <= 1024:
        raise HTTPException(400,'Invalid PPO update epochs or batch size')
    if not 0 <= request.entropy_end <= request.entropy_start <= 1:
        raise HTTPException(400,'Entropy coefficients must satisfy 0 <= end <= start <= 1')
    # Hidden curriculum controls must not block disabled-curriculum runs.
    if request.curriculum_enabled:
        if not 1 <= request.curriculum_first_demands <= 20 or not 1 <= request.curriculum_second_demands <= 20:
            raise HTTPException(400,'Curriculum demand counts must be between 1 and 20')
        if request.curriculum_first_demands > request.curriculum_second_demands:
            raise HTTPException(400,'Curriculum stage 1 cannot have more demands than stage 2')
        if not 1 <= request.curriculum_first_end_pct < request.curriculum_second_end_pct <= 99:
            raise HTTPException(400,'Curriculum transitions must satisfy 1 <= first < second <= 99')
    try:
        scenario = validate_learning_scenario(request.scenario, request.slots, request.slot_seconds)
        data = request.model_dump()
        data['scenario'] = scenario.model_dump(mode='json')
        return learning_jobs.launch(data)
    except ValueError as exc:
        raise HTTPException(400,str(exc))


@app.get('/api/learning/runs/{job_id}')
def learning_run_status(job_id: str):
    try: result=learning_jobs.get(job_id)
    except ValueError as exc:raise HTTPException(400,str(exc))
    if result is None:raise HTTPException(404,'Learning run not found')
    return result


@app.get('/api/learning/runs/{job_id}/metrics')
def learning_run_metrics(job_id: str, since: int = 0, max_points: int = 0):
    if since < 0 or max_points < 0:
        raise HTTPException(400,'since and max_points must be nonnegative')
    try: data=learning_jobs.metrics(job_id, since=since, max_points=max_points)
    except ValueError as exc:raise HTTPException(400,str(exc))
    if data is None:raise HTTPException(404,'Learning run not found')
    return data


@app.get('/api/learning/runs/{job_id}/live')
def learning_run_live(job_id: str):
    try: data=learning_jobs.live(job_id)
    except ValueError as exc: raise HTTPException(400,str(exc))
    if data is None: raise HTTPException(404,'Learning run not found')
    return data


@app.get('/api/learning/runs/{job_id}/evaluation/{episode}')
def learning_run_evaluation(job_id: str, episode: int):
    try: data=learning_jobs.evaluation(job_id,episode)
    except ValueError as exc:raise HTTPException(400,str(exc))
    if data is None:raise HTTPException(404,'That checkpoint has not been evaluated')
    return data


@app.post('/api/learning/runs/{job_id}/stop')
def stop_learning_run(job_id: str):
    try: data=learning_jobs.stop(job_id)
    except ValueError as exc:raise HTTPException(409,str(exc))
    if data is None:raise HTTPException(404,'Learning run not found')
    return data
