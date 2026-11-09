"""Controlled, reproducible Learning Lab preset (not a paper test dataset)."""
from .models import Scenario
from .learning_core import topology_shape


PRESET = 'ontario-compact-v1'


MAX_LEARNING_SLOTS = 288  # bounded for interactive training; one simulation day maximum.


def validate_time_grid(slots: int, slot_seconds: int) -> None:
    if not isinstance(slots, int) or not 1 <= slots <= MAX_LEARNING_SLOTS:
        raise ValueError(f'Learning Lab horizon must have 1–{MAX_LEARNING_SLOTS} slots.')
    if not isinstance(slot_seconds, int) or not 1 <= slot_seconds <= 3600:
        raise ValueError('Slot length must be 1–3600 seconds.')
    if slots * slot_seconds > 86400:
        raise ValueError('Learning horizon cannot exceed 24 hours.')


def preset_scenario(slots=24, slot_seconds=300):
    validate_time_grid(slots, slot_seconds)
    return Scenario.model_validate({
        'ground_stations': [
            {'id':'gs-timmins','name':'Timmins','lat':48.4758,'lon':-81.3305,'capacity_bits':10_000_000},
            {'id':'gs-iroquois','name':'Iroquois Falls','lat':48.7669,'lon':-80.6814,'capacity_bits':10_000_000},
            {'id':'gs-cochrane','name':'Cochrane','lat':49.067,'lon':-81.016,'capacity_bits':10_000_000},
        ],
        'balloons': [
            {'id':'hap-2','name':'HAP 2','lat':48.68,'lon':-81.07,'altitude_km':15,'coverage_km':210,'capacity_bits':18_000_000},
            {'id':'hap-5','name':'HAP 5','lat':48.9,'lon':-80.95,'altitude_km':15,'coverage_km':210,'capacity_bits':18_000_000},
        ],
        'demands': [
            {'id':'d-tim-iro','source':'gs-timmins','target':'gs-iroquois','rate_bps':2600},
            {'id':'d-coch-tim','source':'gs-cochrane','target':'gs-timmins','rate_bps':2200},
            {'id':'d-iro-coch','source':'gs-iroquois','target':'gs-cochrane','rate_bps':2100},
        ],
        'config': {'slots':slots,'slot_seconds':slot_seconds,'weather_source':'manual',
                   'allocation_mode':'scar_q','channel_workers':4},
        'weather_regions':[], 'link_overrides':[],
    })


def preset_metadata(slots=24, slot_seconds=300):
    scenario=preset_scenario(slots,slot_seconds)
    shape=topology_shape(scenario)
    return {'id':PRESET,'label':'Northern Ontario · 3 GS / 2 HAP',
            'description':'Controlled fixed-geometry training sandbox. Real Balloon-QNet rates; no imported test flight or ERA5 weather.',
            'scenario':scenario.model_dump(mode='json'),
            'network':{'ground_stations':shape.n_gs,'haps':shape.n_haps,
                       'demands':shape.n_demands,'directed_links':shape.n_links},
            'policy':{'observation_dim':shape.observation_dim,
                      'logits_dim':shape.logits_dim,'hidden_dim':shape.hidden_dim},
            'slots':slots,'slot_seconds':slot_seconds,'horizon_seconds':slots*slot_seconds}


def validate_learning_scenario(value, slots=24, slot_seconds=300):
    """Validate a user-arranged *static* Studio network before accepting a job.

    The submitted full scenario is captured verbatim except the Lab's explicit
    configured, fixed episode time grid. Neither trajectories nor inferred key rates are
    silently substituted; the original physical setup remains authoritative.
    """
    from pydantic import ValidationError
    validate_time_grid(slots, slot_seconds)
    try:
        scenario=Scenario.model_validate(value) if value is not None else preset_scenario(slots,slot_seconds)
    except ValidationError as exc:
        raise ValueError(f'Invalid learning network: {exc.errors()[0]["msg"]}') from exc
    gs,hap,demand=len(scenario.ground_stations),len(scenario.balloons),len(scenario.demands)
    if not 2<=gs<=8 or not 1<=hap<=6 or not 1<=demand<=20:
        raise ValueError('Learning Lab supports 2–8 GSs, 1–6 HAPs and 1–20 demands in this version.')
    if any(h.trajectory_id for h in scenario.balloons):
        raise ValueError('Training on a fixed topology: remove attached HAP trajectories before starting. The original Studio experiment is unchanged.')
    scenario.config.slots=slots
    scenario.config.slot_seconds=slot_seconds
    # Keep all custom locations, terminals, demands, optical settings, weather,
    # physical link limits, and history references intact.
    topology_shape(scenario)
    return scenario
