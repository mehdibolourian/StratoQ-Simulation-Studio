"""Replace only `simulate` when integrating your real StratoQ pipeline.

Contract: input Scenario, output SimulationResult. Do not couple the browser to
StratoQ setup()'s internal arguments, solver objects, or numpy arrays.
"""
from .models import Scenario, SimulationResult
from .resource_allocator import allocate


def simulate(scenario: Scenario) -> SimulationResult:
    # Future: translate Scenario to your setup(), call channel-cache / routing
    # optimizer / simulator, and convert numpy/Gurobi outputs into frames.
    return allocate(scenario)
