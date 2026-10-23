"""Small, deterministic illustrative *key buffer* simulation.

This deliberately does NOT implement StratoQ's real optimization, trusted-relay
security assumptions, optical turbulence model, or QKD secret key analysis.
It supplies a stable frame-by-frame API for the frontend and later replacement.
"""
import math
from .models import Scenario, LinkState, DemandState, SimulationFrame, SimulationResult, QKPState
from .setup import build_links


def rate_for_link(link: dict, scenario: Scenario, slot: int) -> float:
    # Deliberately simplified path attenuation and variation.
    distance_factor = math.exp(-link["distance_km"] / 75)
    geometry_factor = max(0.20, math.sin(math.radians(link["elevation_deg"])))**0.50
    atmosphere_factor = 10**(-link["weather_loss_db"] / 10)
    variation = 0.90 + 0.10 * math.sin(0.38 * slot + sum(ord(c) for c in link["id"]) * 0.1)
    if not link["enabled"] or not link["in_range"]:
        return 0.0
    return max(0, scenario.config.base_rate_bps * distance_factor
               * geometry_factor * atmosphere_factor * variation)


def allocate(scenario: Scenario) -> SimulationResult:
    candidates = build_links(scenario)
    duration = scenario.config.slot_seconds
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

    for slot in range(scenario.config.slots):
        rates = {link["id"]: rate_for_link(link, scenario, slot) for link in candidates}
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
            slot=slot, time_seconds=slot * duration,
            links=link_states, demands=demand_states, qkps=qkp_states,
            stored_bits_total=round(sum(buffers.values()), 1),
            served_bps_total=round(sum(d.served_bps for d in demand_states), 2)))

    average_served = sum(f.served_bps_total for f in frames) / len(frames)
    average_requested = sum(d.rate_bps for d in scenario.demands)
    return SimulationResult(frames=frames, summary={
        "slots": len(frames), "links": len(candidates),
        "average_served_bps": round(average_served, 2),
        "average_satisfaction": round(average_served / average_requested, 4) if average_requested else 1.0,
        "final_stored_bits": frames[-1].stored_bits_total,
    })
