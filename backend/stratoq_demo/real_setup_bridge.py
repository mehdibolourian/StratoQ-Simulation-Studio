"""Build data.py-compatible payloads WITHOUT importing the real StratoQ stack.

The upstream setup.py uses GS(lg,la,N_RX,N_TX,A_MAX,tag),
HAP(lg[t],la[t],H[t],N_RX,N_TX,A_MAX,tag),
LINK(n1,n2,V[t],W[t],K_MAX[t]) and system(T,THETA,G).
Here we return plain serializable constructor arguments for future integration.
We create both directed links per physical GS-HAP pair, matching the uploaded
init_setup_real_offline/online functions. Per-link W is (fog,rain,snow).

NOTE: Actual calculate_key_rate_mac currently receives GLOBAL weather arrays;
spatially heterogeneous per-link W needs a physical-layer API extension.
"""
from .models import Scenario
from .setup import build_links, balloon_weather
from .trajectories import scenario_at, horizon_seconds


def to_real_setup_payload(scenario: Scenario) -> dict:
    duration = scenario.config.slot_seconds
    horizon = horizon_seconds(scenario)
    slots = min(1500, int(horizon // duration) + 1) if horizon is not None else scenario.config.slots
    gs = [{"id": g.id, "args": [g.lon % 360, g.lat, g.n_rx, g.n_tx, g.capacity_bits, g.name]}
          for g in scenario.ground_stations]
    steps = [scenario_at(scenario, t * duration)[0] for t in range(slots)]
    haps = []
    for h in scenario.balloons:
        sequence = [next(b for b in sample.balloons if b.id == h.id) for sample in steps]
        haps.append({"id": h.id, "args": [
            [p.lon % 360 for p in sequence], [p.lat for p in sequence],
            [p.altitude_km for p in sequence], h.n_rx, h.n_tx,
            h.capacity_bits, h.name]})
    histories = {}
    for sample in steps:
        for link in build_links(sample):
            histories.setdefault(link['id'], []).append(link)
    links = []
    for lid, history in histories.items():
        g, h = lid.split(':', 1)
        V = [x['visibility_km'] for x in history]
        W = [list(x['weather_flags']) for x in history]
        # A placeholder rate bound, NOT an actual calculated K_MAX series.
        K = [0.0 if not x['enabled'] or not x['in_range'] else
             x['capacity_limit_bps'] if x['capacity_limit_bps'] is not None else
             scenario.config.base_rate_bps for x in history]
        for source, target in [(g, h), (h, g)]:
            links.append({"source":source, "target":target, "V":V, "W":W, "K_MAX_placeholder":K})
    return {"system": {"T": list(range(slots)), "THETA": duration,
                       "G": [[1 for _ in scenario.balloons] for _ in scenario.ground_stations]},
            "ground_stations": gs, "haps": haps, "links": links,
            "demands": [{"source":d.source, "target":d.target,
                         "K_REQ_bps": [d.rate_bps]*slots} for d in scenario.demands],
            "weather_by_hap": [{h.id: balloon_weather(h, sample)
                                 for h in sample.balloons} for sample in steps]}
