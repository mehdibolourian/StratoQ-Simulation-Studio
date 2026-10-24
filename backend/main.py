"""Development API: uvicorn main:app --reload --port 8000"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from stratoq_demo.models import Scenario, SimulationResult
from stratoq_demo.setup import default_scenario
from stratoq_demo.stratoq_adapter import simulate
from stratoq_demo.trajectories import register

app = FastAPI(title="StratoQ Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "synthetic-demo"}


@app.get("/api/scenario/default", response_model=Scenario)
def get_default_scenario():
    return default_scenario()


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
