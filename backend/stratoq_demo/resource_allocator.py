"""Slot-by-slot SCAR-Q greedy / MCR-Q Monte Carlo + Gurobi allocation.

Optical K_MAX comes exclusively from the existing upstream physical channel.
Link QKP inventories are shared endpoint views, not additive.
"""
import math
import logging

LOGGER = logging.getLogger("uvicorn.error")
from .models import Scenario, LinkState, DemandState, SimulationFrame, SimulationResult, QKPState
from .setup import build_links, balloon_weather
from .physical_setup import create_physical_network
from .trajectories import scenario_at, horizon_seconds
from .era5_weather import scenario_era5
from .allocator_algorithms import select_and_solve_slot, require_gurobi


def allocate(scenario: Scenario, progress=None) -> SimulationResult:
    gp = require_gurobi()  # Fail BEFORE expensive LOWTRAN channel evaluation.
    era5 = scenario_era5(scenario)
    if progress and era5: progress({'stage':'era5-sampling','total':1,'completed':0})
    physical = create_physical_network(scenario, progress=progress)
    candidates = build_links(scenario)
    duration = physical.system.THETA
    slots = physical.slots
    capacity_by_gs = {g.id: g.capacity_bits for g in scenario.ground_stations}
    # A GS's HAP-specific store is capped at the station's total budget / number of optical neighbors.
    hap_capacity = {h.id: h.capacity_bits for h in scenario.balloons}
    gs_degree = {g.id: sum(link["source"] == g.id for link in candidates)
                 for g in scenario.ground_stations}
    hap_degree = {h.id: sum(link["target"] == h.id for link in candidates)
                  for h in scenario.balloons}
    # Each link buffer represents the same shared key material at both ends.
    # It is not two independently generated inventories.
    max_storage = {
        link["id"]: min(
            capacity_by_gs[link["source"]] / max(1, gs_degree[link["source"]]),
            hap_capacity[link["target"]] / max(1, hap_degree[link["target"]]),
        ) for link in candidates
    }
    buffers = {link["id"]: 0.0 for link in candidates}
    frames: list[SimulationFrame] = []
    solver_runs = 0
    gurobi_seconds = 0.
    successful_slot_solves = 0
    activated_slot_count = 0
    slots_without_routes = 0
    gurobi_version = "unknown"

    for slot in range(slots):
        slot_scenario, positions = scenario_at(scenario, slot * duration)
        candidates = build_links(slot_scenario)
        # The authoritative rate series is computed before allocation, once per
        # directed optical link and trajectory time slot.
        rates = {link["id"]: physical.rate_by_link[link["id"]][slot]
                 for link in candidates}
        # The displayed geometry should match the very same physical samples.
        for link in candidates:
            physical_sample = physical.scene_links[(link['source'],link['target'])][slot]
            link['distance_km'] = physical_sample['distance_km']
            link['elevation_deg'] = physical_sample['elevation_deg']
            link['in_range'] = physical_sample['in_range']
            link['weather_loss_db'] = physical_sample['weather_loss_db']
            link['weather_flags'] = physical_sample['weather_flags']
        weather_by_hap = {h.id: balloon_weather(h, slot_scenario) for h in slot_scenario.balloons}
        historical_regions=[]
        historical_metadata={}
        if era5 is not None:
            weather_frame=era5.frame(slot*duration,duration)
            historical_regions=era5.regions(weather_frame,limit=75)
            historical_metadata={'date_utc':era5.day.isoformat(),
                'source':'ERA5 reanalysis', 'visual_cells_shown':len(historical_regions),
                'grid_cells':len(era5.lats)*len(era5.lons),
                'fog':'humidity/low-cloud proxy (not observed fog)',
                'rain_snow':'ERA5 hourly water-equivalent accumulations'}
            for hap in slot_scenario.balloons:
                wx=era5.point(weather_frame,hap.lat,hap.lon)
                current=weather_by_hap[hap.id]
                current['fog']=int(current['fog'] or wx['fog'])
                current['rain']=int(current['rain'] or wx['rain']>0.05)
                current['snow']=int(current['snow'] or wx['snow']>0.05)
        # Reference algorithms: SCAR-Q = one greedy candidate;
        # MCR-Q = N randomized candidate paths each separately optimized
        # with Gurobi. Only the best candidate commits its QKP next-state.
        audit = {}
        paths, solved = select_and_solve_slot(
            slot_scenario, rates, buffers, max_storage, duration,
            scenario.config.allocation_mode,
            seed=scenario.config.allocator_seed + slot,
            n_samples=scenario.config.mcr_samples, gp=gp, trace=audit)
        served, live, stored, activated, buffers, objective_bits = solved
        # Count real calls that returned from Gurobi's optimize(), not planned calls.
        solver_runs += audit['candidate_solves']
        gurobi_seconds += audit['gurobi_runtime_seconds']
        successful_slot_solves += int(audit['solver_status'] == 'OPTIMAL')
        activated_slot_count += int(bool(activated))
        slots_without_routes += int(not paths)
        gurobi_version = audit['gurobi_version']
        if slot < 3 or slot == slots-1 or slot % max(1,slots//10) == 0:
            LOGGER.info('[StratoQ solver] slot=%s/%s algorithm=%s Gurobi=%s models=%s paths=%s active_links=%s '
                        'positive_KMAX=%s served_bits=%.3f solver_seconds=%.6f',
                        slot+1, slots, scenario.config.allocation_mode, audit['solver_status'],
                        audit['candidate_solves'], audit['selected_paths'], len(activated),
                        audit['positive_capacity_links'], objective_bits, audit['gurobi_runtime_seconds'])
        path_by_demand = {p.demand_id:p for p in paths}
        link_use = {link['id']:0. for link in candidates}
        for p in paths:
            if served.get(p.demand_id,0.) > 1e-7:
                link_use[p.uplink_id] += served[p.demand_id]
                link_use[p.downlink_id] += served[p.demand_id]
        demand_states = []
        for d in scenario.demands:
            achieved = max(0., served.get(d.id,0.))
            selected_path = path_by_demand.get(d.id)
            demand_states.append(DemandState(
                id=d.id, source=d.source, target=d.target,
                requested_bps=d.rate_bps, served_bps=round(achieved, 2),
                path=[d.source, selected_path.hap_id, d.target]
                     if achieved > 1e-7 and selected_path else [],
                status='served' if achieved >= d.rate_bps-1e-6
                else 'partial' if achieved > 1e-7 else 'blocked'))

        link_states = [LinkState(
            **link, capacity_bps=round(rates[link['id']],2),
            stored_bits=round(buffers[link['id']],1),
            used_bps=round(link_use[link['id']],2),
            active=rates[link['id']] > 0.01,
            activated=link['id'] in activated,
            allocated=link_use[link['id']] > 1e-7,
        ) for link in candidates]
        # Aggregate the endpoint copies of the shared per-link key inventories.
        # HAP/GS totals are logical endpoint views (not additive physical bits).
        node_cap = {**capacity_by_gs, **hap_capacity}
        qkp_states = []
        for node_id, cap in node_cap.items():
            stored = sum(buffers[link["id"]] for link in candidates
                         if node_id in (link["source"], link["target"]))
            qkp_states.append(QKPState(
                node_id=node_id, stored_bits=round(stored, 1),
                capacity_bits=round(cap, 1),
                fill_fraction=round(min(1.0, stored / cap), 5)))
        frames.append(SimulationFrame(
            slot=slot, time_seconds=slot * duration, positions=positions,
            weather_by_hap=weather_by_hap,
            historical_weather_regions=historical_regions,
            historical_weather_metadata=historical_metadata,
            links=link_states, demands=demand_states, qkps=qkp_states,
            stored_bits_total=round(sum(buffers.values()), 1),
            served_bps_total=round(sum(d.served_bps for d in demand_states), 2),
            optimizer=audit))
        if progress: progress({"stage":"allocation", "total":slots,"completed":slot+1})

    average_served = sum(f.served_bps_total for f in frames) / len(frames)
    average_requested = sum(d.rate_bps for d in scenario.demands)
    if progress: progress({"stage":"allocation", "total":slots, "completed":slots, "cached":physical.rate_stats["cached"], "computed":physical.rate_stats["computed"]})
    return SimulationResult(engine="balloon-qnet-theoretical", frames=frames, summary={
        "slots": len(frames), "links": len(candidates),
        "average_served_bps": round(average_served, 2),
        "average_satisfaction": round(average_served / average_requested, 4) if average_requested else 1.0,
        "final_stored_bits": frames[-1].stored_bits_total,
        "physical_evaluations": physical.rate_stats["computed"],
        "cached_evaluations": physical.rate_stats["cached"],
        "algorithm": scenario.config.allocation_mode,
        "mcr_samples": scenario.config.mcr_samples if scenario.config.allocation_mode == 'mcr_q' else 0,
        "allocator_seed": scenario.config.allocator_seed,
        "gurobi_slot_solves": solver_runs,
        "gurobi_optimized_models": solver_runs,
        "gurobi_runtime_seconds": round(gurobi_seconds, 6),
        "gurobi_version": gurobi_version,
        "optimal_slots": successful_slot_solves,
        "slots_with_activated_links": activated_slot_count,
        "slots_without_selected_paths": slots_without_routes,
    })
