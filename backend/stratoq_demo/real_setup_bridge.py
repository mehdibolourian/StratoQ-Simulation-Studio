"""JSON export of the materialized StratoQ-compatible objects and upstream theoretical K_MAX."""
from .physical_setup import create_physical_network

def to_real_setup_payload(scenario):
    p = create_physical_network(scenario)
    return {
        "engine": "balloon-qnet-theoretical",
        "system": {"T": list(p.system.T), "THETA": p.system.THETA,
                   "G": p.system.G.tolist()},
        "ground_stations": [
            {"id":g.tag,"args":[g.lg,g.la,g.N_RX,g.N_TX,g.A_MAX,g.tag]}
            for g in p.ground_stations],
        "haps": [
            {"id":h.tag,"args":[h.lg,h.la,h.H,h.N_RX,h.N_TX,h.A_MAX,h.tag]}
            for h in p.balloons],
        "links": [
            {"source":l.n1.tag,"target":l.n2.tag,"V":l.V,"W":l.W,
             "K_MAX":l.K_MAX} for l in p.links],
        "demands": [
            {"source":d.n1.tag,"target":d.n2.tag,"K_REQ_bps":d.K_REQ}
            for d in p.demands],
    }
