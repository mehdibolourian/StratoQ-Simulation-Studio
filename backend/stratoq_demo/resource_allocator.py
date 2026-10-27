"""Slot-by-slot placeholder resource allocator consuming upstream BB84 capacities.

Only allocation is illustrative; the optical rate is computed by physical_setup.
Link key inventories are shared copies at both endpoints, not additive.
"""
import math
import random
from .models import Scenario, LinkState, DemandState, SimulationFrame, SimulationResult, QKPState
from .setup import build_links, balloon_weather
from .physical_setup import create_physical_network
from .trajectories import scenario_at, horizon_seconds
from .era5_weather import scenario_era5


def allocate(scenario: Scenario, progress=None) -> SimulationResult:
    rng = random.Random(scenario.config.allocator_seed)
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
        for link in candidates:
            lid = link["id"]
            buffers[lid] = min(max_storage[lid], buffers[lid] + rates[lid] * duration)

        demand_states = []
        link_use = {link["id"]: 0.0 for link in candidates}
        # Simple greedy allocator: a deterministic test seam for a future ILP / heuristic.
        for demand in scenario.demands:
            options = []
            for balloon in scenario.balloons:
                l1 = f"{demand.source}:{balloon.id}"
                l2 = f"{demand.target}:{balloon.id}"
                if l1 in buffers and l2 in buffers and rates[l1] > 0 and rates[l2] > 0:
                    options.append((min(buffers[l1], buffers[l2]) / duration, l1, l2, balloon.id))
            if options:
                # Explicitly a placeholder policy, not StratoQ's optimizer.
                # Random mode is seed-reproducible and selects among feasible
                # GS-HAP-GS paths. Greedy mode favors the largest inventory.
                if scenario.config.allocation_mode == 'random':
                    possible_bps, l1, l2, balloon_id = rng.choice(options)
                else:
                    possible_bps, l1, l2, balloon_id = max(options)
                served_bps = min(demand.rate_bps, possible_bps)
                used = served_bps * duration
                link_use[l1] += served_bps
                link_use[l2] += served_bps
                buffers[l1] = max(0., buffers[l1] - used)
                buffers[l2] = max(0., buffers[l2] - used)
                path = [demand.source, balloon_id, demand.target] if served_bps > 0 else []
            else:
                served_bps, path = 0., []
            demand_states.append(DemandState(
                id=demand.id, source=demand.source, target=demand.target,
                requested_bps=demand.rate_bps, served_bps=round(served_bps, 2),
                path=path, status="served" if served_bps >= demand.rate_bps - 1e-6
                else "partial" if served_bps > 0 else "blocked"))

        link_states = [LinkState(
            **link, capacity_bps=round(rates[link["id"]], 2),
            stored_bits=round(buffers[link["id"]], 1),
            used_bps=round(link_use[link["id"]], 2), active=rates[link["id"]] > 0.01
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
            served_bps_total=round(sum(d.served_bps for d in demand_states), 2)))

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
    })
