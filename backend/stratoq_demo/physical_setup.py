"""Materialize upstream StratoQ objects and run original balloon_qnet theory."""
from dataclasses import dataclass
import numpy as np
from .stratoq_data import gs, hap, link, demand, system
from .setup import build_links
from .trajectories import scenario_at, horizon_seconds
from .demand_profiles import demand_rates
from .era5_weather import scenario_era5
from balloon_qnet.studio_analytical import geometry
from .real_rates import calculate_key_rate_mac_real

@dataclass
class PhysicalNetwork:
    system: system
    ground_stations: list
    balloons: list
    links: list
    demands: list
    scene_links: dict
    rate_by_link: dict
    geometry_by_link: dict
    slots: int
    rate_stats: dict | None = None

def create_physical_network(scenario, progress=None):
    dt=scenario.config.slot_seconds
    era5=scenario_era5(scenario)
    horizon=horizon_seconds(scenario)
    slots=max(1,int(np.ceil(horizon/dt))) if horizon is not None else scenario.config.slots
    if era5 is not None:
        # Historical weather belongs to one UTC day; never extrapolate.
        slots=min(slots,(86400+dt-1)//dt)
    snapshots=[scenario_at(scenario, t*dt)[0] for t in range(slots)]
    syst=system(range(slots),dt,np.ones((len(scenario.ground_stations),len(scenario.balloons)),dtype=int))
    gnodes=[gs(g.lon%360.,g.lat,g.n_rx,g.n_tx,g.capacity_bits,g.id)
            for g in scenario.ground_stations]
    hnodes=[]
    for h in scenario.balloons:
        sequence=[next(x for x in snap.balloons if x.id==h.id) for snap in snapshots]
        hnodes.append(hap([x.lon%360. for x in sequence],
                          [x.lat for x in sequence],
                          [x.altitude_km for x in sequence],
                          h.n_rx,h.n_tx,h.capacity_bits,h.id))
    record_map={}
    geo_map={}
    for t,snap in enumerate(snapshots):
        per_slot={(x['source'],x['target']):x for x in build_links(snap)}
        for g in scenario.ground_stations:
            for h in scenario.balloons:
                key=(g.id,h.id)
                record=per_slot[key].copy()
                slant,el,horiz=geometry(g.lat,g.lon,
                    next(x for x in snap.balloons if x.id==h.id).lat,
                    next(x for x in snap.balloons if x.id==h.id).lon,
                    next(x for x in snap.balloons if x.id==h.id).altitude_km)
                record['distance_km']=slant
                record['elevation_deg']=el
                record['in_range']=record['in_range'] and el>0
                if era5 is not None:
                    sampled=era5.frame(t*dt,dt)
                    hap_sample=next(x for x in snap.balloons if x.id==h.id)
                    era5_loss,era5_flags=era5.link_attenuation(g,hap_sample,sampled,
                        wavelength_nm=scenario.config.optical.wavelength_nm)
                    # Manual and ERA5 losses add in dB; binary flags are OR.
                    record['weather_loss_db']+=era5_loss
                    record['weather_flags']=tuple(int(a or b) for a,b in zip(record['weather_flags'],era5_flags))
                record_map.setdefault(key,[]).append(record)
                geo_map.setdefault(key,[]).append((slant,el,horiz))
        if era5 is not None and progress and (t % max(1,slots//40)==0 or t==slots-1):
            progress({'stage':'era5-sampling','total':slots,'completed':t+1,'cached':0,'computed':0})
    directed=[]
    for g in gnodes:
        for h in hnodes:
            history=record_map[(g.tag,h.tag)]
            V=[r['visibility_km'] for r in history]
            W=[r['weather_flags'] for r in history]
            for n1,n2 in [(g,h),(h,g)]:
                directed.append(link(n1,n2,V[:],W[:],[0.]*slots))
    profiles=demand_rates(scenario, slots, dt)
    demands=[demand(profiles[d.id],
                    next(g for g in gnodes if g.tag==d.source),
                    next(g for g in gnodes if g.tag==d.target))
             for d in scenario.demands]
    result=PhysicalNetwork(syst,gnodes,hnodes,directed,demands,record_map,{},geo_map,slots)
    directed_rates, result.rate_stats = calculate_key_rate_mac_real(
        directed,result,scenario.config.optical,progress=progress,
        max_workers=scenario.config.channel_workers)
    for l,values in zip(directed,directed_rates):
        l.K_MAX[:]=values
    # Conservative shared key generation rate per GS-HAP pair: both
    # uplink and downlink must be supported by the channel configuration.
    for g in gnodes:
        for h in hnodes:
            pair=(g.tag,h.tag)
            forward=next(l.K_MAX for l in directed if l.n1 is g and l.n2 is h)
            backward=next(l.K_MAX for l in directed if l.n1 is h and l.n2 is g)
            result.rate_by_link[f'{g.tag}:{h.tag}']=[min(a,b) for a,b in zip(forward,backward)]
    return result
