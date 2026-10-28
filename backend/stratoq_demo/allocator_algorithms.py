"""Notebook-grounded SCAR-Q (greedy) and MCR-Q (Monte Carlo) policies.

The uploaded `hap-qkd-online-path-based-dynamic-NEW.ipynb` defines both policies:
scarq_policy sorts scarce demands and least-contended feasible one-HAP paths;
mcr_policy samples randomized assignments and retains the most served keys
AFTER solving online_new for every sample. This module adapts those policies
onto Studio's GS-HAP-GS physical links and the per-slot Gurobi key-flow LP.
"""
from collections import Counter
import random
from dataclasses import dataclass
import os

EPS = 1e-7

@dataclass(frozen=True)
class PathOption:
    demand_id: str
    source: str
    target: str
    hap_id: str
    uplink_id: str
    downlink_id: str
    requested_bps: float
    available_bps: float


def require_gurobi():
    try:
        import gurobipy as gp
        # Imported lazily; no mock optimizer or silent fallback.
        return gp
    except ImportError as exc:
        raise RuntimeError('Gurobi is required for SCAR-Q/MCR-Q. Install in the backend environment: python -m pip install gurobipy; configure a valid Gurobi license.') from exc


def candidate_paths(scenario, rates, buffers, duration):
    """Only simple GS -> HAP -> GS paths; physical link names remain GS:HAP."""
    paths = {}
    for d in scenario.demands:
        options = []
        if d.rate_bps <= EPS:
            paths[d.id] = options
            continue  # An inactive zero-rate slot must not reserve a HAP terminal.
        for h in scenario.balloons:
            a, b = f'{d.source}:{h.id}', f'{d.target}:{h.id}'
            avail = min(max(0., rates.get(a, 0.)) + max(0., buffers.get(a, 0.))/duration,
                        max(0., rates.get(b, 0.)) + max(0., buffers.get(b, 0.))/duration)
            if avail > EPS:
                options.append(PathOption(d.id, d.source, d.target, h.id, a, b, d.rate_bps, avail))
        paths[d.id] = options
    return paths


def choose_paths(scenario, rates, buffers, duration, algorithm, rng=None):
    """Choose one set of routes using the notebook's policy definitions.

    SCAR-Q: only *fully feasible* fresh-fresh OR QKP-QKP paths; fewer
    feasible options first, higher demand second; least-contended route.
    MCR-Q: random demand order, then uniform random feasible one-HAP
    route, respecting Tx/Rx availability. One call is ONE Monte Carlo sample.
    The best-of-samples comparison is in select_and_solve_slot().

    The notebook has a binary per-HAP uplink/downlink terminal limit;
    Studio also respects configured ground-station port limits.
    """
    if algorithm not in ('scar_q', 'mcr_q'):
        raise ValueError(f'Unsupported allocation algorithm: {algorithm}')
    if duration <= 0:
        raise ValueError('Slot duration must be positive')
    rng = rng if rng is not None else random.Random(42)
    all_options = candidate_paths(scenario, rates, buffers, duration)
    if algorithm == 'scar_q':
        # Exact test in notebook: (both fresh K_MAX >= K_REQ) OR
        # (both stored QKP / THETA >= K_REQ); not a sum of partial sources.
        options = {
            d.id: [p for p in all_options[d.id]
                   if (rates.get(p.uplink_id, 0.) + EPS >= d.rate_bps
                       and rates.get(p.downlink_id, 0.) + EPS >= d.rate_bps)
                   or (buffers.get(p.uplink_id, 0.) / duration + EPS >= d.rate_bps
                       and buffers.get(p.downlink_id, 0.) / duration + EPS >= d.rate_bps)]
            for d in scenario.demands
        }
        contention = Counter(lid for ps in options.values() for p in ps
                             for lid in (p.uplink_id, p.downlink_id))
        # Python's stable sort preserves scenario order for exact ties.
        demands = sorted(scenario.demands,
                         key=lambda d: (len(options[d.id]), -d.rate_bps))
    else:
        # Notebook's mcr_policy random.sample() shuffles active demands.
        options = all_options
        demands = rng.sample(list(scenario.demands), len(scenario.demands))

    used = Counter()
    nodes = [*scenario.ground_stations, *scenario.balloons]
    n_rx = {node.id: node.n_rx for node in nodes}
    n_tx = {node.id: node.n_tx for node in nodes}
    selected = []
    for d in demands:
        feasible = []
        # Notebook uses one-HAP paths, with one HAP TX and RX per path.
        for p in options[d.id]:
            terminals = ((p.source, 'tx'), (p.hap_id, 'rx'),
                         (p.hap_id, 'tx'), (p.target, 'rx'))
            if all(used[token] < (n_tx if token[1] == 'tx' else n_rx)[token[0]]
                   for token in terminals):
                feasible.append((p, terminals))
        if not feasible:
            continue
        if algorithm == 'scar_q':
            # Notebook: rank feasible paths solely by aggregate link contention.
            p, terminals = min(feasible, key=lambda item:
                               contention[item[0].uplink_id] +
                               contention[item[0].downlink_id])
        else:
            # Notebook: uniform random feasible path, not max-capacity routing.
            p, terminals = rng.choice(feasible)
        selected.append(p)
        for token in terminals:
            used[token] += 1
    return selected


def select_and_solve_slot(scenario, rates, buffers, max_storage, duration,
                          algorithm, seed=42, n_samples=3, gp=None, trace=None):
    """Select paths AND solve the Gurobi LP for the requested heuristic.

    SCAR-Q solves one greedy candidate. MCR-Q independently samples
    `n_samples` randomized candidate assignments, solves each with the
    actual Gurobi model, and retains the largest served-key objective.
    Critically, QKP is updated ONLY from the winning candidate; losing
    Monte Carlo samples never change the simulation's storage state.
    """
    if algorithm not in ('scar_q', 'mcr_q'):
        raise ValueError(f'Unsupported allocation algorithm: {algorithm}')
    if not isinstance(n_samples, int) or n_samples < 1:
        raise ValueError('MCR-Q sample count must be a positive integer')
    rng = random.Random(seed)
    best_paths, best_result = None, None
    n_trials = n_samples if algorithm == 'mcr_q' else 1
    if trace is not None:
        trace.update(algorithm=algorithm, candidate_solves=0, gurobi_runtime_seconds=0.,
                     gurobi_variable_count=0, gurobi_constraint_count=0,
                     selected_paths=0, positive_capacity_links=sum(v > EPS for v in rates.values()),
                     candidate_paths=sum(len(p) for p in candidate_paths(scenario,rates,buffers,duration).values()))
    for sample in range(n_trials):
        paths = choose_paths(scenario, rates, buffers, duration, algorithm, rng=rng)
        audit = {} if trace is not None else None
        result = solve_slot(paths, rates, buffers, max_storage, duration, gp=gp,
                            diagnostics=audit) if trace is not None else solve_slot(
                                paths, rates, buffers, max_storage, duration, gp=gp)
        if trace is not None:
            trace['candidate_solves'] += int(audit['optimize_called'])
            trace['gurobi_runtime_seconds'] += audit['runtime_seconds']
            trace['gurobi_variable_count'] = max(trace['gurobi_variable_count'], audit['variables'])
            trace['gurobi_constraint_count'] = max(trace['gurobi_constraint_count'], audit['constraints'])
            trace['solver_status'] = audit['status']
            trace['gurobi_version'] = audit['gurobi_version']
            trace['last_candidate_paths'] = len(paths)
        # Primary objective: achieved served-key volume, not raw optical capacity.
        if best_result is None or result[-1] > best_result[-1] + EPS:
            best_paths, best_result = paths, result
            if trace is not None: trace['winning_sample'] = sample + 1
    if trace is not None:
        trace['selected_paths'] = len(best_paths or [])
        trace['activated_links'] = len(best_result[3]) if best_result else 0
        trace['served_bits'] = float(best_result[-1]) if best_result else 0.
        trace['gurobi_runtime_seconds'] = round(trace['gurobi_runtime_seconds'], 6)
        if not best_paths:
            trace['selection_note'] = ('No feasible full-rate paths under SCAR-Q. Try a lower demand rate or MCR-Q for partial-rate routing.'
                                       if algorithm == 'scar_q' else
                                       'No feasible path has positive fresh or stored-key capacity for both optical hops.')
        elif not best_result[3]:
            trace['selection_note'] = 'Selected demand routes used stored keys only; no optical links were newly activated.'
        else:
            trace['selection_note'] = 'Active optical links are highlighted in gold; unselected links remain muted.'
    return best_paths, best_result


def solve_slot(paths, rates, buffers, max_storage, duration, gp=None, diagnostics=None):
    """Gurobi LP, explicitly splitting fresh generation r_1 and stored QKP r_2.

    Key-rate conservation on each selected GS-HAP-GS path:
      r_h[d] = r_1[d,l] + r_2[d,l]  (for both optical hops)
      Σ_d r_1[d,l] ≤ K_MAX[l],   θ Σ_d r_2[d,l] ≤ A_prev[l].
    QKP conservation: A_next = A_prev + θ*(K_MAX*z - r_1 - r_2) - discarded.
    The per-link buffer upper bound enforces the storage capacity.
    """
    gp = gp or require_gurobi()
    model = gp.Model('stratoq_online_allocation')
    # Default quiet for 24-1440 slot simulations. Opt in to genuine Gurobi logs:
    # STRATOQ_GUROBI_LOG=1 python -m uvicorn main:app --port 8000
    model.Params.OutputFlag = 1 if os.environ.get('STRATOQ_GUROBI_LOG') == '1' else 0
    # As in the supplied notebook, a path fully supported by QKP can consume
    # stored keys without turning on either optical connection. Otherwise,
    # enable only the links whose old inventory cannot serve the demand.
    activated = {
        lid for p in paths for lid in (p.uplink_id, p.downlink_id)
        if max(0.,rates.get(lid,0.)) > EPS
        and buffers.get(lid,0.) / duration + EPS < p.requested_bps
    }
    model.Params.Method = 1
    model.Params.FeasibilityTol = 1e-8
    r_h = {}; r_1 = {}; r_2 = {}
    for p in paths:
        d=p.demand_id
        r_h[d] = model.addVar(lb=0.,ub=p.requested_bps,name=f'r_h_{d}')
        for i,lid in enumerate((p.uplink_id,p.downlink_id)):
            r_1[d,i] = model.addVar(lb=0.,name=f'r_1_{d}_{i}')
            r_2[d,i] = model.addVar(lb=0.,name=f'r_2_{d}_{i}')
            model.addConstr(r_1[d,i]+r_2[d,i] == r_h[d],name=f'flow_{d}_{i}')
    a_next = {}; discarded = {}
    for ix,lid in enumerate(sorted(set([*rates,*buffers]))):
        members=[(p.demand_id,i) for p in paths for i,e in enumerate((p.uplink_id,p.downlink_id)) if e == lid]
        capacity = max(0., rates.get(lid,0.)) if lid in activated else 0.
        previous = max(0., buffers.get(lid,0.))
        a_next[lid] = model.addVar(lb=0.,ub=max_storage[lid],name=f'A_next_{ix}')
        discarded[lid] = model.addVar(lb=0.,name=f'discard_{ix}')
        model.addConstr(gp.quicksum(r_1[k] for k in members) <= capacity,
                        name=f'fresh_{ix}')
        model.addConstr(gp.quicksum(r_2[k] for k in members) * duration <= previous,
                        name=f'stored_{ix}')
        model.addConstr(a_next[lid] == previous + duration * (
            capacity - gp.quicksum(r_1[k]+r_2[k] for k in members)) - discarded[lid],
                        name=f'qkp_conservation_{ix}')
    # Lexicographic: first maximize end-to-end served bits, then retain as many
    # unused keys as can fit in the endpoint-limited QKP capacities.
    model.ModelSense = gp.GRB.MAXIMIZE
    model.setObjectiveN(gp.quicksum(r_h.values()) * duration, index=0, priority=2, name='serve_keys')
    model.setObjectiveN(gp.quicksum(a_next.values()), index=1, priority=1, name='retain_qkp')
    model.optimize()
    if diagnostics is not None:
        diagnostics.update(optimize_called=True, status=('OPTIMAL' if model.Status == gp.GRB.OPTIMAL else str(model.Status)),
                           runtime_seconds=float(model.Runtime), variables=int(model.NumVars),
                           constraints=int(model.NumConstrs),
                           gurobi_version='.'.join(map(str, gp.gurobi.version())))
    if model.Status != gp.GRB.OPTIMAL:
        raise RuntimeError(f'Gurobi failed to solve slot allocation: status {model.Status}')
    served = {d:float(v.X) for d,v in r_h.items()}
    live = Counter(); saved = Counter()
    for p in paths:
        for i,lid in enumerate((p.uplink_id,p.downlink_id)):
            live[lid]+=max(0.,float(r_1[p.demand_id,i].X))
            saved[lid]+=max(0.,float(r_2[p.demand_id,i].X))
    # Read the QKP next-state directly from the solved optimization variables.
    next_buffers={lid:float(v.X) for lid,v in a_next.items()}
    return served, dict(live), dict(saved), activated, next_buffers, sum(served.values())*duration
