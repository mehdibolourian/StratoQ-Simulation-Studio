"""Full-horizon Gurobi MILP inspired by the uploaded offline.py (problem=2).

Unlike online SCAR-Q/MCR-Q, binary path/link activations, generated-key rates,
stored-key consumption, and QKP inventory are optimized JOINTLY across all slots.
Studio's supported routes are one-HAP GS→HAP→GS, not arbitrary multi-hop paths;
therefore explicit single-HAP path binaries replace general graph MTZ variables.
"""
import logging
import math

LOG = logging.getLogger('uvicorn.error')
EPS = 1e-7


def solve_offline(scenario, snapshots, rates_by_slot, capacity_by_link,
                  demand_profiles, seconds, gp, progress=None):
    GRB = gp.GRB
    T = len(snapshots)
    demands = scenario.demands
    links = [f'{g.id}:{h.id}' for g in scenario.ground_stations for h in scenario.balloons]
    gs_ids = {g.id for g in scenario.ground_stations}
    model = gp.Model('stratoq_offline_full_horizon')
    model.Params.OutputFlag = 0
    model.Params.MIPGap = scenario.config.optimality_gap
    model.Params.TimeLimit = scenario.config.optimal_time_limit_seconds
    # Each selected path consumes one TX and RX on its HAP; source GS Tx and
    # destination GS Rx are also limited, as in the online path selector.
    z = {}; flow = {}; fresh = {}; saved = {}
    path_members = {}; by_demand_slot = {}; by_link_slot = {}
    by_gs_tx = {}; by_gs_rx = {}; by_hap_rx = {}; by_hap_tx = {}
    for t, records in enumerate(snapshots):
        available = {record['id']: bool(record['enabled'] and record['in_range']) for record in records}
        for d in demands:
            ds = (d.id, t)
            by_demand_slot[ds] = []
            for h in scenario.balloons:
                left = f'{d.source}:{h.id}'
                right = f'{d.target}:{h.id}'
                if not (available.get(left, False) and available.get(right, False)):
                    continue
                key = d.id, h.id, t
                required = max(0., demand_profiles[d.id][t])
                z[key] = model.addVar(vtype=GRB.BINARY, name=f'z_{d.id}_{h.id}_{t}')
                flow[key] = model.addVar(lb=0., ub=required, name=f'flow_{d.id}_{h.id}_{t}')
                model.addConstr(flow[key] <= required * z[key])
                by_demand_slot[ds].append(key)
                by_gs_tx.setdefault((d.source, t), []).append(z[key])
                by_gs_rx.setdefault((d.target, t), []).append(z[key])
                by_hap_rx.setdefault((h.id, t), []).append(z[key])
                by_hap_tx.setdefault((h.id, t), []).append(z[key])
                path_members[key] = (left, right)
                for leg, lid in enumerate((left, right)):
                    fresh[key, leg] = model.addVar(lb=0., ub=required, name=f'r1_{d.id}_{h.id}_{leg}_{t}')
                    saved[key, leg] = model.addVar(lb=0., ub=required, name=f'r2_{d.id}_{h.id}_{leg}_{t}')
                    model.addConstr(fresh[key, leg] + saved[key, leg] == flow[key])
                    by_link_slot.setdefault((lid, t), []).append((key, leg))
            model.addConstr(gp.quicksum(z[k] for k in by_demand_slot[ds]) <= 1,
                            name=f'one_path_{d.id}_{t}')
        if progress and (t % max(1, T//12) == 0):
            progress({'stage': 'offline-model', 'total': T, 'completed': t+1})
    for gs in scenario.ground_stations:
        for t in range(T):
            model.addConstr(gp.quicksum(by_gs_tx.get((gs.id, t), ())) <= gs.n_tx)
            model.addConstr(gp.quicksum(by_gs_rx.get((gs.id, t), ())) <= gs.n_rx)
    for h in scenario.balloons:
        for t in range(T):
            model.addConstr(gp.quicksum(by_hap_rx.get((h.id, t), ())) <= h.n_rx)
            model.addConstr(gp.quicksum(by_hap_tx.get((h.id, t), ())) <= h.n_tx)
    inventory = {}
    activation = {}
    discarded = {}
    for lid in links:
        maximum = float(capacity_by_link[lid])
        for t in range(T+1):
            inventory[lid, t] = model.addVar(lb=0., ub=maximum, name=f'QKP_{lid}_{t}')
        model.addConstr(inventory[lid, 0] == 0., name=f'empty_QKP_{lid}')
        for t in range(T):
            capacity = max(0., float(rates_by_slot[t].get(lid, 0.)))
            activation[lid, t] = model.addVar(vtype=GRB.BINARY,
                                               ub=1. if capacity > EPS else 0., name=f'y_{lid}_{t}')
            members = by_link_slot.get((lid, t), ())
            model.addConstr(activation[lid, t] <= gp.quicksum(z[key] for key, _ in members),
                            name=f'route_activation_{lid}_{t}')
            total_new = gp.quicksum(fresh[key, leg] for key, leg in members)
            total_old = gp.quicksum(saved[key, leg] for key, leg in members)
            model.addConstr(total_new <= capacity * activation[lid, t], name=f'fresh_capacity_{lid}_{t}')
            # A stored key must exist at the beginning of the slot; newly
            # generated keys cannot be double-counted as stored consumption.
            model.addConstr(seconds * total_old <= inventory[lid, t], name=f'stored_availability_{lid}_{t}')
            # Without overflow the capacity*y - fresh surplus is FORCED into a
            # finite QKP, making long slots infeasible whenever
            # seconds*(capacity - demand) exceeds the remaining buffer space.
            # Model unused generated keys as discardable, like solve_slot().
            # Discard is a *rate* (bits/s) for better numerical scaling; it
            # is multiplied by seconds in the inventory balance below.
            discarded[lid, t] = model.addVar(lb=0., ub=capacity,
                                             name=f'discard_rate_{lid}_{t}')
            model.addConstr(discarded[lid, t] <= capacity * activation[lid, t] - total_new,
                            name=f'discard_only_generated_{lid}_{t}')
            model.addConstr(inventory[lid, t+1] == inventory[lid, t]
                            + seconds * (capacity * activation[lid, t] - total_new
                                         - total_old - discarded[lid, t]),
                            name=f'QKP_carry_{lid}_{t}')
    # Case 2 objective from the uploaded offline.py: maximize total served bits.
    primary = seconds * gp.quicksum(flow.values())
    # Use a single objective: Gurobi's reported MIPGap then applies exactly
    # to served keys rather than to a secondary QKP-storage objective.
    model.setObjective(primary, GRB.MAXIMIZE)
    if progress: progress({'stage':'offline-solve','total':1,'completed':0})
    model.optimize()
    if progress: progress({'stage':'offline-solve','total':1,'completed':1})
    status = model.Status
    if model.SolCount < 1:
        raise RuntimeError(f'Offline Gurobi model found no incumbent (status={status}). '
                           'Try a larger time limit, a larger MIP gap, or fewer slots.')
    status_name = {GRB.OPTIMAL:'OPTIMAL', GRB.TIME_LIMIT:'TIME_LIMIT',
                   GRB.SUBOPTIMAL:'SUBOPTIMAL', GRB.INTERRUPTED:'INTERRUPTED'}.get(status, f'STATUS_{status}')
    gap = float(model.MIPGap) if model.IsMIP else 0.
    if not math.isfinite(gap):
        gap = float('nan')
    per_slot = []
    for t in range(T):
        selected = {}
        served = {}
        fresh_by_link = {lid: 0. for lid in links}
        saved_by_link = {lid: 0. for lid in links}
        for d in demands:
            keys = by_demand_slot[d.id, t]
            chosen = next((key for key in keys if z[key].X > .5), None)
            rate = sum(max(0., flow[key].X) for key in keys)
            served[d.id] = rate
            if chosen is not None and rate > EPS:
                selected[d.id] = chosen[1]
            for key in keys:
                for leg, lid in enumerate(path_members[key]):
                    fresh_by_link[lid] += max(0., fresh[key,leg].X)
                    saved_by_link[lid] += max(0., saved[key,leg].X)
        activated = {lid for lid in links if activation[lid,t].X > .5}
        per_slot.append({
            'served': served, 'paths': selected, 'fresh': fresh_by_link,
            'saved': saved_by_link, 'activated': activated,
            'buffers': {lid:max(0.,float(inventory[lid,t+1].X)) for lid in links},
            'discarded_bits': {lid:max(0.,float(discarded[lid,t].X))*seconds for lid in links},
            'optimizer': {
                'solver_status': status_name, 'candidate_solves': 1 if t == 0 else 0,
                'gurobi_version': '.'.join(map(str,gp.gurobi.version())),
                'gurobi_runtime_seconds': float(model.Runtime) if t == 0 else 0.,
                'gurobi_variable_count': model.NumVars,
                'gurobi_constraint_count': model.NumConstrs,
                'selected_paths': len(selected), 'activated_links': len(activated),
                'positive_capacity_links': sum(v > EPS for v in rates_by_slot[t].values()),
                'selection_note': f'Full-horizon mixed-integer model; achieved MIP gap {gap:.3%}.',
                'achieved_mip_gap':gap if math.isfinite(gap) else -1.,
                'objective_bound_bits':float(model.ObjBound) if model.IsMIP and math.isfinite(float(model.ObjBound)) else -1.,
                'offline_full_horizon': True,
                'discarded_bits_total': sum(max(0.,float(discarded[lid,t].X))*seconds for lid in links),
            },
        })
    return per_slot, {
        'gurobi_status':status_name, 'gurobi_runtime_seconds':float(model.Runtime),
        'gurobi_optimized_models':1, 'gurobi_variable_count':model.NumVars,
        'gurobi_constraint_count':model.NumConstrs, 'achieved_mip_gap':gap if math.isfinite(gap) else -1.,
        'requested_mip_gap':scenario.config.optimality_gap,
        'optimality_certified': status == GRB.OPTIMAL,
        'offline_objective_served_bits': sum(sum(s['served'].values()) for s in per_slot) * seconds,
        'offline_discarded_bits_total': sum(sum(s['discarded_bits'].values()) for s in per_slot),
    }
