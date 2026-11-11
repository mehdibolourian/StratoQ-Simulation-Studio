"""Isolated genuine PPO training job for the Learning Lab.

No synthetic optical rates, no fabricated learning curves. Real GS-HAP key rates
are computed once by the existing upstream Balloon-QNet physical engine, and
all policy / SCAR-Q / MCR-Q candidates use Studio's exact Gurobi slot LP.
The controlled preset is an *adaptation* of paper methodology, not reproduction
of the published five-flight training and held-out three-topology experiments.
"""
from __future__ import annotations
import argparse
import copy
import json
import logging
import os
from pathlib import Path
import random
import struct
import sys
import time
import traceback
import numpy as np
from .learning_core import (topology_shape, observation, port_mask, demand_indices,
                            make_policy, sample_choices, ppo_update, paper_shaped_reward,
                            validate_reward_shape)
from .learning_presets import preset_scenario, validate_learning_scenario, PRESET
from .allocator_algorithms import (PathOption, require_gurobi, select_and_solve_slot,
                                   solve_slot)
from .physical_setup import create_physical_network
from .setup import build_links, balloon_weather
from .trajectories import scenario_at
from .models import LinkState, DemandState, QKPState, SimulationFrame
from .demand_profiles import demand_rates

log=logging.getLogger('stratoq.learning')


def write_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,allow_nan=False,indent=2),encoding='utf-8')
    os.replace(tmp,path)


def append_metric(job_dir, metric):
    """Append one complete training record, then publish its seek offset.

    The fixed-width index makes polling O(new episodes), not O(all episodes).
    Existing metrics.json readers remain supported for short runs.
    """
    directory=Path(job_dir)
    row=(json.dumps(metric,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
    with (directory/'metrics.jsonl').open('ab') as stream:
        offset=stream.tell()
        stream.write(row)
        stream.flush()
    # An offset is published only after its data line is fully written.
    with (directory/'metrics.offsets').open('ab') as index:
        index.write(struct.pack('<Q',offset))
        index.flush()


def base_rates_and_storage(scenario, physical):
    candidates=build_links(scenario)
    gs_degrees={g.id:sum(l['source']==g.id for l in candidates) for g in scenario.ground_stations}
    hap_degrees={h.id:sum(l['target']==h.id for l in candidates) for h in scenario.balloons}
    gs={g.id:g for g in scenario.ground_stations}
    haps={h.id:h for h in scenario.balloons}
    storage={l['id']:min(gs[l['source']].capacity_bits/max(1,gs_degrees[l['source']]),
                         haps[l['target']].capacity_bits/max(1,hap_degrees[l['target']])) for l in candidates}
    rates=[{l['id']:float(physical.rate_by_link[l['id']][t]) for l in candidates}
           for t in range(physical.slots)]
    return candidates,rates,storage


def rate_schedule(scenario, slots, duration, rng=None):
    """Vary positive demand levels by episode; evaluation uses fixed means.

    No artificial optical rate variation: channel capacities remain upstream.
    Demand multipliers are explicitly a training distribution, not observed data.
    """
    raw=demand_rates(scenario,slots,duration)
    by_demand={}
    for d in scenario.demands:
        scale=float(rng.uniform(.70,1.30)) if rng is not None else 1.
        # deterministic within-episode demand pattern across the fixed horizon
        phase=float(scenario.demands.index(d))*.85
        by_demand[d.id]=[max(0.01, float(r)*scale*(1.+.3*np.sin(2*np.pi*t/max(1,slots)+phase)))
                           for t,r in enumerate(raw[d.id])]
    return by_demand


def curriculum_schedule(schedule, episode, episodes, rng, *, enabled=True, first_demands=1, second_demands=2, first_end_pct=12, second_end_pct=30):
    """Optional, gradual demand-count curriculum on a fixed network.

    The progression applies to episode *training data*, not the policy shape.
    Checkpoint evaluations always use every demand for comparability.
    """
    names=list(schedule)
    n=len(names)
    if not enabled:
        active=n
    elif episode <= max(1,round(first_end_pct*episodes/100)):
        active=min(n,max(1,int(first_demands)))
    elif episode <= max(1,round(second_end_pct*episodes/100)):
        active=min(n,max(1,int(second_demands)))
    else:
        active=n
    chosen=set(str(x) for x in rng.choice(names,size=active,replace=False))
    result={k:(v if k in chosen else [0.0]*len(v)) for k,v in schedule.items()}
    return result,active


def scenario_for_slot(scenario, schedule, slot):
    snap=scenario.model_copy(deep=True)
    for d in snap.demands:
        d.rate_bps=float(schedule[d.id][slot])
    return snap


def feasible_routes(scenario, rates):
    # Only nonzero physically supported two-hop routes are valid PPO actions.
    # GS port conflicts are subsequently handled by autoregressive masks.
    return {(d.id,h.id) for d in scenario.demands for h in scenario.balloons
            if rates.get(f'{d.source}:{h.id}',0.)>1.e-8
            and rates.get(f'{d.target}:{h.id}',0.)>1.e-8}


def choices_to_paths(scenario, choices, rates):
    result=[]
    for h, choice in zip(scenario.balloons,choices):
        if choice<=0: continue
        d=scenario.demands[choice-1]
        up=f'{d.source}:{h.id}';down=f'{d.target}:{h.id}'
        result.append(PathOption(d.id,d.source,d.target,h.id,up,down,d.rate_bps,
                                 min(rates[up],rates[down])))
    return result


def slot_inputs(scenario, physical, rates, buffers, schedule, slot):
    actual=scenario_for_slot(scenario,schedule,slot)
    requested={d.id:d.rate_bps for d in actual.demands}
    obs=observation(actual,physical,slot,buffers,requested)
    mask=port_mask(actual,feasible_routes(actual,rates))
    # Curriculum-inactive demands must not consume policy actions/terminals.
    for idx,demand in enumerate(actual.demands):
        if requested[demand.id] <= 0:
            mask[:,idx+1]=False
    return actual,requested,obs,mask


def run_episode(policy, scenario, physical, all_rates, max_storage, gp,
                schedule, port_data, training=False, rng_seed=42, make_frames=False, progress=None,
                reward_shape=None):
    buffers={key:0. for key in max_storage}
    duration=scenario.config.slot_seconds
    rollout=[]; total_reward=0.;total_served=0.;total_requested=0.; frames=[]
    for t,rates in enumerate(all_rates):
        actual,requested,obs,base_mask=slot_inputs(scenario,physical,rates,buffers,schedule,t)
        choices,logp,value=sample_choices(policy,obs,base_mask,port_data,
                                          deterministic=not training)
        paths=choices_to_paths(actual,choices,rates)
        prev_buffers=buffers.copy()
        served,live,saved,activated,buffers,bits=solve_slot(
            paths,rates,buffers,max_storage,duration,gp=gp)
        if training:
            # Both reward baselines start from *the same* QKP state as the agent.
            _,scar_result=select_and_solve_slot(actual,rates,prev_buffers,max_storage,
                duration,'scar_q',seed=rng_seed+t,gp=gp)
            _,mcr_result=select_and_solve_slot(actual,rates,prev_buffers,max_storage,
                duration,'mcr_q',seed=rng_seed+t,n_samples=1,gp=gp)
            reward=paper_shaped_reward(served,scar_result[0],mcr_result[0],requested,reward_shape)
        else:
            # Evaluation reward is satisfaction-shaped in the same *scale*;
            # checkpoint comparison is based on delivered keys, not reward.
            satisfaction=[min(1.,served.get(did,0.)/max(1.e-8,req))
                          for did,req in requested.items() if req>0]
            reward=float(np.mean(satisfaction)) if satisfaction else 0.
        total_reward+=reward
        total_served+=bits
        total_requested+=sum(requested.values())*duration
        if progress is not None:
            progress({'slots_done':t+1,'slots_total':len(all_rates),
                      'partial_reward':total_reward/(t+1),
                      'partial_satisfaction':total_served/total_requested if total_requested else 1.,
                      'partial_served_bits':total_served,
                      'partial_requested_bits':total_requested})
        if training:
            rollout.append({'obs':obs,'mask':base_mask,'choices':choices,
                            'logp':logp,'value':value,'reward':reward})
        if make_frames:
            candidates=build_links(actual)
            positions={h.id: {'lat':h.lat,'lon':h.lon,'altitude_km':h.altitude_km}
                       for h in actual.balloons}
            paths_by_d={p.demand_id:p.hap_id for p in paths}
            link_use={lid:0. for lid in rates}
            for d in actual.demands:
                if d.id in paths_by_d:
                    for lid in (f'{d.source}:{paths_by_d[d.id]}',f'{d.target}:{paths_by_d[d.id]}'):
                        link_use[lid]+=max(0.,served.get(d.id,0.))
            states=[]
            for l in candidates:
                sample=physical.scene_links[(l['source'],l['target'])][t]
                l.update({k:sample[k] for k in ('distance_km','elevation_deg','in_range',
                                                'weather_loss_db','weather_flags')})
                states.append(LinkState(**l,capacity_bps=round(rates[l['id']],2),
                                        stored_bits=round(buffers[l['id']],1),
                                        used_bps=round(link_use[l['id']],2),
                                        fresh_used_bps=round(max(0.,live.get(l['id'],0.)),2),
                                        qkp_used_bps=round(max(0.,saved.get(l['id'],0.)),2),
                                        active=rates[l['id']]>1.e-8,
                                        activated=l['id'] in activated,
                                        allocated=link_use[l['id']]>1.e-8))
            demands=[]
            for d in actual.demands:
                delivered=max(0.,served.get(d.id,0.))
                path=[d.source,paths_by_d[d.id],d.target] if delivered>1.e-8 and d.id in paths_by_d else []
                demands.append(DemandState(id=d.id,source=d.source,target=d.target,
                                           requested_bps=d.rate_bps,served_bps=round(delivered,2),
                                           path=path,status='served' if delivered>=d.rate_bps-1.e-6
                                           else 'partial' if delivered>1.e-8 else 'blocked'))
            qkps=[]
            for n in [*actual.ground_stations,*actual.balloons]:
                stored=sum(buffers[l['id']] for l in candidates
                           if n.id in (l['source'],l['target']))
                qkps.append(QKPState(node_id=n.id,stored_bits=round(stored,1),
                          capacity_bits=n.capacity_bits,
                          fill_fraction=min(1.,stored/n.capacity_bits)))
            frames.append(SimulationFrame(slot=t,time_seconds=t*duration,links=states,
                          positions=positions,weather_by_hap={h.id:balloon_weather(h,actual)
                                                               for h in actual.balloons},
                          demands=demands,qkps=qkps,
                          stored_bits_total=round(sum(buffers.values()),1),
                          served_bps_total=round(sum(served.values()),2),
                          optimizer={'algorithm':'stratoq-ppo',
                                     'checkpoint_note':'Frozen PPO checkpoint',
                                     'slot_reward':round(reward,5)}).model_dump(mode='json'))
    return {'reward':total_reward/len(all_rates),
            'satisfaction':total_served/total_requested if total_requested else 1.,
            'served_bits':total_served,'requested_bits':total_requested,
            'rollout':rollout,'frames':frames}


def evaluate_baseline(scenario,all_rates,max_storage,gp,schedule,algorithm,seed,progress=None):
    duration=scenario.config.slot_seconds
    buffers={lid:0. for lid in max_storage}
    total_served=0.
    for t,rates in enumerate(all_rates):
        actual=scenario_for_slot(scenario,schedule,t)
        _,solved=select_and_solve_slot(actual,rates,buffers,max_storage,duration,
             algorithm,seed=seed+t,n_samples=1,gp=gp)
        buffers=solved[4]
        total_served+=solved[-1]
        if progress is not None: progress({'algorithm':algorithm,
                 'completed':t+1,'total':len(all_rates)})
    return total_served


def train(job_dir):
    import torch
    job_dir=Path(job_dir)
    cfg=json.loads((job_dir/'config.json').read_text())
    status={'id':job_dir.name,'status':'running','stage':'physical-rates',
            'episode':0,'episodes':cfg['episodes'],'checkpoints':[],
            'error':None,'started_at':time.time()}
    def update():write_json(job_dir/'status.json',status)
    update()
    seed=int(cfg['seed']);random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    torch.set_num_threads(1)
    scenario=validate_learning_scenario(cfg.get('scenario'),cfg['slots'],cfg.get('slot_seconds',300))
    if cfg['preset']!=PRESET:raise ValueError('Learning preset changed; refusal to use mismatched configuration')
    shape=topology_shape(scenario)
    write_json(job_dir/'topology.json',dict(
       scenario=scenario.model_dump(mode='json'),shape=vars(shape),
       note='Fresh PPO weights for this exact topology. No cross-topology generalization claim.',
       physics='Balloon-QNet actual upstream channel, Studio Gurobi per-slot LP'))
    gp=require_gurobi()
    # Verify license before doing costly channel physics.
    trial=gp.Model('learning_license_probe');trial.Params.OutputFlag=0
    trial.addVar(name='x');trial.optimize();trial.dispose()
    def physical_progress(info):
        status['physical_progress'] = {k:info.get(k) for k in ('stage','total','completed','cached','computed','workers')}
        update()
    physical=create_physical_network(scenario,progress=physical_progress)
    if physical.slots!=cfg['slots']:
        raise ValueError('Physical simulation did not return the configured number of slots')
    _,all_rates,max_storage=base_rates_and_storage(scenario,physical)
    if not any(feasible_routes(scenario, rates) for rates in all_rates):
        raise ValueError('No physically feasible two-hop path for any demand under the real optical model; cannot train.')
    policy=make_policy(shape)
    optimizer=torch.optim.Adam(policy.parameters(),lr=float(cfg.get('learning_rate',2.e-4)))
    reward_shape=validate_reward_shape(cfg)
    status['reward_shape']=vars(reward_shape).copy()  # Visible, reproducible run metadata.
    update()
    ports=demand_indices(scenario)
    rng=np.random.default_rng(seed)
    eval_schedule=rate_schedule(scenario,cfg['slots'],scenario.config.slot_seconds)
    # Make the first genuine curve point available before slow heuristic
    # reference evaluations. No baseline is needed for frozen evaluation.
    status['stage']='initial-evaluation';update()
    def stream(stage, episode, data):
        # Atomically publish measured progress *during* each slot, including
        # checkpoint 0. The chart does not wait for episode completion.
        status['stage']=stage
        status['slot_progress']={'episode':episode,'completed':data['slots_done'],
                                 'total':data['slots_total']}
        status['updated_at']=time.time()
        update()
        write_json(job_dir/'live.json',{'stage':stage,'episode':episode,**data,
                                          'episode_complete':False})

    def save_checkpoint(episode):
        status['stage']='checkpoint-evaluation' if episode else 'initial-evaluation'
        status.pop('slot_progress',None)
        update()
        phase='checkpoint-evaluation' if episode else 'initial-evaluation'
        result=run_episode(policy,scenario,physical,all_rates,max_storage,gp,
            eval_schedule,ports,training=False,make_frames=True,
            progress=lambda data:stream(phase,episode,data))
        checkpoint={'episode':episode,'evaluation_reward':result['reward'],
                    'evaluation_satisfaction':result['satisfaction'],
                    'evaluation_served_bits':result['served_bits']}
        torch.save({'state_dict':policy.state_dict(),'shape':vars(shape),
                    'preset':PRESET,'slots':cfg['slots'],
                    'slot_seconds':scenario.config.slot_seconds,'seed':seed,
                    'reward_shape':vars(reward_shape)},
                    job_dir/f'checkpoint_{episode:06d}.pt')
        write_json(job_dir/f'evaluation_{episode:06d}.json',{
            'episode':episode,'summary':{k:result[k] for k in
               ('reward','satisfaction','served_bits','requested_bits')},
            'frames':result['frames'],
            'baselines':status.get('baselines',{}),
            'reward_shape':vars(reward_shape),
            'scenario':scenario.model_dump(mode='json')})
        status['checkpoints'].append(checkpoint)
        status.pop('slot_progress',None)
        status['updated_at']=time.time()
        update()
        write_json(job_dir/'live.json',{'stage':phase,'episode':episode,
            'slots_done':len(all_rates),'slots_total':len(all_rates),
            'partial_reward':result['reward'],
            'partial_satisfaction':result['satisfaction'],
            'episode_complete':True})

    # Real frozen checkpoint 0 appears as soon as the optical model is ready.
    # The prior implementation ran two full heuristic passes BEFORE episode 1,
    # often making the UI appear stalled for an entire presentation.
    save_checkpoint(0)
    status.update(stage='training',shape=vars(shape));update()
    # Per-episode JSONL is append-only, avoiding quadratic rewriting of the
    # entire metric history during long experiments. Small runs retain the
    # historical metrics.json file for compatibility with existing tools.
    metrics=[]
    for ep in range(1,cfg['episodes']+1):
        full_schedule=rate_schedule(scenario,cfg['slots'],scenario.config.slot_seconds,rng)
        schedule,active_demands=curriculum_schedule(full_schedule,ep,cfg['episodes'],rng,
               enabled=cfg.get('curriculum_enabled',True),
               first_demands=cfg.get('curriculum_first_demands',1),
               second_demands=cfg.get('curriculum_second_demands',2),
               first_end_pct=cfg.get('curriculum_first_end_pct',12),
               second_end_pct=cfg.get('curriculum_second_end_pct',30))
        status.update(stage='training',curriculum_active_demands=active_demands)
        status.pop('slot_progress',None)
        update()
        collected=run_episode(policy,scenario,physical,all_rates,max_storage,gp,
                            schedule,ports,training=True,rng_seed=seed+ep,
                            progress=lambda data:stream('training',ep,data),
                            reward_shape=reward_shape)
        status['stage']='ppo-update';update()
        ent=float(cfg.get('entropy_start',.008)) + (float(cfg.get('entropy_end',.0003))-
              float(cfg.get('entropy_start',.008)))*ep/max(1,cfg['episodes'])
        update_stats=ppo_update(policy,optimizer,collected['rollout'],ports,
                       gamma=float(cfg.get('gamma',.99)),
                       gae_lambda=float(cfg.get('gae_lambda',.95)),
                       clip=float(cfg.get('clip',.2)),
                       entropy_coef=ent,ppo_epochs=int(cfg.get('ppo_epochs',8)),
                       batch_size=int(cfg.get('batch_size',16)))
        line={'episode':ep,'active_demands':active_demands,'train_reward':collected['reward'],
              'train_satisfaction':collected['satisfaction'],
              'train_served_bits':collected['served_bits'],'entropy_coef':ent,**update_stats}
        append_metric(job_dir,line)
        # Preserve the original JSON format for short runs and old tests;
        # large runs use only the append-only stream to bound disk I/O.
        if ep <= 100:
            metrics.append(line)
            write_json(job_dir/'metrics.json',metrics)
        elif ep == 101:
            metrics.clear()
            (job_dir/'metrics.json').unlink(missing_ok=True)
        status.update(episode=ep,stage='training',updated_at=time.time())
        update()
        write_json(job_dir/'live.json',{'stage':'training','episode':ep,
            'slots_done':len(all_rates),'slots_total':len(all_rates),
            'partial_reward':collected['reward'],
            'partial_satisfaction':collected['satisfaction'],
            'episode_complete':True})
        if ep % cfg['checkpoint_every']==0 or ep==cfg['episodes']:
            save_checkpoint(ep)

    # Heuristic comparison is optional and runs *after* all PPO episodes.
    # It is expensive (2 complete LP sweeps), so the default live demo avoids
    # introducing unexplained minutes of extra work before automatic completion.
    if cfg.get('compare_baselines',False):
        status['stage']='baseline-evaluation';status.pop('slot_progress',None);update()
        def baseline_progress(data):
            status['baseline_progress']=data
            status['stage']='baseline-evaluation'
            status['updated_at']=time.time()
            update()
        scar_bits=evaluate_baseline(scenario,all_rates,max_storage,gp,eval_schedule,'scar_q',seed+10000,
                                    progress=baseline_progress)
        mcr_bits=evaluate_baseline(scenario,all_rates,max_storage,gp,eval_schedule,'mcr_q',seed+10000,
                                   progress=baseline_progress)
        baselines={'scar_q_bits':scar_bits,'mcr_q_bits':mcr_bits}
        write_json(job_dir/'baselines.json',baselines)
        for c in status['checkpoints']:
            f=job_dir/f"evaluation_{c['episode']:06d}.json"
            item=json.loads(f.read_text())
            item['baselines']=baselines
            write_json(f,item)
        status['baselines']=baselines
    status.pop('slot_progress',None)
    if cfg['episodes']:
        write_json(job_dir/'live.json',{'stage':'complete','episode':line['episode'],
            'slots_done':len(all_rates),'slots_total':len(all_rates),
            'partial_reward':line['train_reward'],
            'partial_satisfaction':line['train_satisfaction'],
            'episode_complete':True})
    status.update(status='complete',stage='complete',episode=cfg['episodes'],finished_at=time.time(),updated_at=time.time())
    update()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job-dir',required=True)
    args=parser.parse_args();job_dir=Path(args.job_dir)
    try:train(job_dir)
    except Exception as exc:
        log.exception('Learning job failed')
        try:
            prev=json.loads((job_dir/'status.json').read_text())
        except Exception:prev={}
        prev.update(status='failed',stage='failed',error=f'{type(exc).__name__}: {exc}')
        write_json(job_dir/'status.json',prev)
        raise


if __name__=='__main__':main()
