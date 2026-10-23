"""Development API: uvicorn main:app --reload --port 8000"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stratoq_demo.models import Scenario, SimulationResult
from stratoq_demo.setup import default_scenario
from stratoq_demo.stratoq_adapter import simulate

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
