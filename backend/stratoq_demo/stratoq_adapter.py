"""Replace only `simulate` when integrating your real StratoQ pipeline.

Contract: input Scenario, output SimulationResult. Do not couple the browser to
StratoQ setup()'s internal arguments, solver objects, or numpy arrays.
"""
from .models import Scenario, SimulationResult
from .resource_allocator import allocate


def simulate(scenario: Scenario, progress=None) -> SimulationResult:
    # Physical GS/HAP/link initialization and analytical K_MAX are performed
    # by physical_setup; only demand allocation remains a demo heuristic.
    return allocate(scenario, progress=progress)
