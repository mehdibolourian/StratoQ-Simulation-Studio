"""Topology-sized StratoQ PPO policy and constrained HAP assignment sampler.

The model's input/output dimensions are derived from the *current* network.
A differently sized network starts with different weights; no cross-topology
checkpoint reuse or claim of universal generalization is implied.

This learning demonstration uses Studio's physical link/LP semantics. It is not
an assertion of bit-for-bit reproduction of the canonical paper experiments.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class PolicyShape:
    n_gs: int
    n_haps: int
    n_demands: int
    n_links: int
    observation_dim: int
    logits_dim: int
    hidden_dim: int


def topology_shape(scenario) -> PolicyShape:
    gs, haps, demands = len(scenario.ground_stations), len(scenario.balloons), len(scenario.demands)
    if gs < 2 or haps < 1 or demands < 1:
        raise ValueError('Learning requires at least two GSs, one HAP and one demand.')
    links = 2 * gs * haps  # directed feature representation (GS->HAP and HAP->GS)
    obs = 7*links + 6*demands
    # Bounded width scaling; both observation and actor head sizes scale exactly.
    width = max(64, min(256, 32*math.ceil(obs/128)))
    return PolicyShape(gs, haps, demands, links, obs, haps*(demands+1), width)


def port_mask(scenario, feasible):
    """Feasible HAP/demand paths, with categorical column 0 reserved for idle."""
    mask = np.zeros((len(scenario.balloons),len(scenario.demands)+1),dtype=bool)
    mask[:,0] = True
    for h_idx,h in enumerate(scenario.balloons):
        for d_idx,d in enumerate(scenario.demands):
            mask[h_idx,d_idx+1] = (h.n_rx>0 and h.n_tx>0 and (d.id,h.id) in feasible)
    return mask


def sequential_masks(base_mask, chosen, src_indices, dst_indices, tx_limits, rx_limits):
    """Autoregressive action masks; no duplicate demand or excess GS terminals.

    ``chosen`` contains the *previous* sampled choices as well as the current
    one when assessing a recorded action. This is deterministic and reusable
    for PPO log-probability recomputation.
    """
    base = np.asarray(base_mask,dtype=bool)
    n_haps, categories=base.shape
    used_tx=np.zeros(len(tx_limits),dtype=int)
    used_rx=np.zeros(len(rx_limits),dtype=int)
    used_demands=set()
    masks=[]
    for h in range(n_haps):
        allowed=base[h].copy()
        for idx in range(1,categories):
            d=idx-1
            if (d in used_demands or used_tx[src_indices[d]]>=tx_limits[src_indices[d]]
                or used_rx[dst_indices[d]]>=rx_limits[dst_indices[d]]):
                allowed[idx]=False
        allowed[0]=True
        masks.append(allowed)
        if h < len(chosen) and int(chosen[h]) > 0:
            selected=int(chosen[h])-1
            if not allowed[selected+1]:
                raise ValueError('Action violates HAP/demand/GS terminal mask')
            used_demands.add(selected)
            used_tx[src_indices[selected]]+=1
            used_rx[dst_indices[selected]]+=1
    return np.stack(masks)


def demand_indices(scenario):
    names={g.id:i for i,g in enumerate(scenario.ground_stations)}
    return ([names[d.source] for d in scenario.demands],
            [names[d.target] for d in scenario.demands],
            [g.n_tx for g in scenario.ground_stations],
            [g.n_rx for g in scenario.ground_stations])


def observation(scenario, physical, slot, buffers, requested):
    """7 per directed link + 6 per demand, no zero padding to maximum topology.

    Uses actual upstream directed K_MAX for link features, while online Studio's
    LP uses the conservative shared pair rate min(uplink,downlink). This is
    explicitly a Studio adaptation of the paper's observation/action model.
    """
    ref_lat=np.mean([g.lat for g in scenario.ground_stations])
    ref_lon=np.mean([g.lon for g in scenario.ground_stations])
    def xy(lat,lon):
        dl=((lon-ref_lon+180)%360)-180
        return np.asarray((111.195*dl*math.cos(math.radians(ref_lat)),
                           111.195*(lat-ref_lat)),dtype=float)
    coords=[xy(g.lat,g.lon) for g in scenario.ground_stations]
    coords += [xy(h.lat,h.lon) for h in scenario.balloons]
    scale=max(1.,*(float(np.max(np.abs(x))) for x in coords))
    gs_coords={g.id:xy(g.lat,g.lon)/scale for g in scenario.ground_stations}
    hap_coords={h.id:xy(h.lat,h.lon)/scale for h in scenario.balloons}
    vec=[]
    for link in physical.links:  # physical builds 2 links per GS/HAP in stable order
        g=link.n1 if link.n1.tag in gs_coords else link.n2
        h=link.n2 if link.n2.tag in hap_coords else link.n1
        pair=f'{g.tag}:{h.tag}'
        k=max(0.,float(link.K_MAX[slot]))
        if link.n1.tag in gs_coords:
            first,second=gs_coords[g.tag],hap_coords[h.tag]
        else:
            first,second=hap_coords[h.tag],gs_coords[g.tag]
        active=float(physical.rate_by_link[pair][slot]>1.e-8)
        vec.extend([np.log10(1+max(0.,buffers.get(pair,0.)))/8.,
                    np.log10(1+k)/6., *first,*second,active])
    for d in scenario.demands:
        vec.extend([np.log10(1+max(0.,requested[d.id]))/5.,
                    *gs_coords[d.source],*gs_coords[d.target],
                    float(requested[d.id]>1.e-8)])
    obs=np.asarray(vec,dtype=np.float32)
    if not np.all(np.isfinite(obs)):
        raise ValueError('Nonfinite physics observation')
    expected=topology_shape(scenario).observation_dim
    if len(obs)!=expected:
        raise ValueError(f'Observation topology mismatch: {len(obs)} != {expected}')
    return obs


def paper_shaped_reward(achieved, scarq, mcrq, requested):
    """Per-demand heuristic-relative shaped reward as in paper-aligned Eq.14.

    Dictionaries keyed by *stable demand ID*, avoiding the active-demand
    reindexing bug present in some notebook helper variants.
    """
    scores=[]
    for demand_id,requirement in requested.items():
        if requirement<=0: continue
        rho=min(1.,max(0.,achieved.get(demand_id,0.))/(requirement+1e-8))
        scar=min(1.,max(0.,scarq.get(demand_id,0.))/(requirement+1e-8))
        mcr=min(1.,max(0.,mcrq.get(demand_id,0.))/(requirement+1e-8))
        hi,lo=max(scar,mcr),min(scar,mcr)
        if rho>=0.95: r=1.
        elif rho>=hi: r=0.6+0.4*(rho-hi)
        elif rho>=lo: r=0.1+0.1*(rho-lo)/(hi-lo+1e-8)
        else: r=-(lo-rho)
        scores.append(r)
    return float(np.mean(scores)) if scores else 0.


def make_policy(shape):
    """Lazy torch dependency: existing Studio simulation imports stay unchanged."""
    import torch
    from torch import nn

    class Residual(nn.Module):
        def __init__(self,width):
            super().__init__()
            self.net=nn.Sequential(nn.Linear(width,width),nn.Tanh(),nn.Linear(width,width))
        def forward(self,x):
            return torch.tanh(x+self.net(x))

    class ActorCritic(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder=nn.Sequential(nn.Linear(shape.observation_dim,shape.hidden_dim),nn.Tanh(),
                                       Residual(shape.hidden_dim),Residual(shape.hidden_dim))
            self.actor=nn.Linear(shape.hidden_dim,shape.logits_dim)
            self.critic=nn.Linear(shape.hidden_dim,1)
        def forward(self,x):
            y=self.encoder(x)
            return (self.actor(y).reshape(-1,shape.n_haps,shape.n_demands+1),
                    self.critic(y).squeeze(-1))
    return ActorCritic()


def evaluate_choices(logits, actions, base_masks, port_data):
    """Exact joint log probabilities for the autoregressive constrained sampler.

    Returns (sum(logp), mean(entropy)) for batch for use by PPO.
    """
    import torch
    from torch.distributions import Categorical
    sources,targets,tx,rx=port_data
    probs=[]; entropies=[]
    for i in range(logits.shape[0]):
        choices=actions[i].tolist()
        masks=sequential_masks(base_masks[i],choices,sources,targets,tx,rx)
        allowed=torch.as_tensor(masks,device=logits.device,dtype=torch.bool)
        distributions=Categorical(logits=logits[i].masked_fill(~allowed,-1.e9))
        choices_tensor=torch.as_tensor(choices,device=logits.device,dtype=torch.long)
        probs.append(distributions.log_prob(choices_tensor).sum())
        entropies.append(distributions.entropy().mean())
    return torch.stack(probs),torch.stack(entropies)


def sample_choices(policy, obs, base_mask, port_data, deterministic=False):
    import torch
    from torch.distributions import Categorical
    src,dst,tx,rx=port_data
    with torch.no_grad():
        logits,values=policy(torch.as_tensor(obs).reshape(1,-1))
        logits=logits[0]
        choices=[]
        for h in range(logits.shape[0]):
            allowed=sequential_masks(base_mask,choices,src,dst,tx,rx)[h]
            distribution=Categorical(logits=logits[h].masked_fill(
                ~torch.as_tensor(allowed,dtype=torch.bool),-1.e9))
            choice=distribution.probs.argmax() if deterministic else distribution.sample()
            choices.append(int(choice.item()))
        all_lp,_=evaluate_choices(logits[None],torch.tensor([choices]),
                                  np.asarray([base_mask]),port_data)
    return choices,float(all_lp.item()),float(values.item())


def ppo_update(policy, optimizer, rollout, port_data, gamma=.99, gae_lambda=.95,
               clip=.2, ppo_epochs=5, batch_size=64, entropy_coef=.01):
    """On-policy PPO with GAE, policy clipping, value loss and entropy bonus."""
    import torch
    if not rollout: return {'policy_loss':0.,'value_loss':0.,'entropy':0.}
    rewards=np.asarray([r['reward'] for r in rollout],dtype=np.float32)
    values=np.asarray([r['value'] for r in rollout],dtype=np.float32)
    advantages=np.zeros_like(rewards)
    gae=0.
    for t in reversed(range(len(rollout))):
        following=values[t+1] if t+1<len(rollout) else 0.
        td=rewards[t]+gamma*following-values[t]
        gae=td+gamma*gae_lambda*gae if t+1<len(rollout) else td
        advantages[t]=gae
    returns=advantages+values
    if len(advantages)>1:
        advantages=(advantages-advantages.mean())/(advantages.std()+1e-8)
    observations=torch.tensor(np.stack([r['obs'] for r in rollout]),dtype=torch.float32)
    choices=torch.tensor([r['choices'] for r in rollout],dtype=torch.long)
    bases=np.stack([r['mask'] for r in rollout])
    olds=torch.tensor([r['logp'] for r in rollout],dtype=torch.float32)
    targets=torch.tensor(returns,dtype=torch.float32)
    adv=torch.tensor(advantages,dtype=torch.float32)
    stats=[]
    for _ in range(ppo_epochs):
        for ids in torch.randperm(len(rollout)).split(batch_size):
            logits, v=policy(observations[ids])
            logp,entropy=evaluate_choices(logits,choices[ids],bases[ids.numpy()],port_data)
            ratio=(logp-olds[ids]).exp()
            actor_loss=-torch.minimum(ratio*adv[ids],
                      torch.clamp(ratio,1.-clip,1.+clip)*adv[ids]).mean()
            critic_loss=((v-targets[ids])**2).mean()
            ent=entropy.mean()
            loss=actor_loss + .5*critic_loss-entropy_coef*ent
            optimizer.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(),.5)
            optimizer.step()
            stats.append((actor_loss.item(),critic_loss.item(),ent.item()))
    averaged=np.mean(stats,axis=0)
    return dict(zip(('policy_loss','value_loss','entropy'),map(float,averaged)))
