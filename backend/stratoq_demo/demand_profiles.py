"""Deterministic, slot-aligned GS-pair demand rates (bits/s).

The user-entered rate_bps is the *time-weighted mean over the chosen horizon*.
Gaussian patterns repeat every 24h and are normalized on the actual slot grid.
"""
import math


def _periodic_gaussian(hour, centre, width):
    delta = abs((hour - centre + 12.) % 24. - 12.)
    return math.exp(-0.5 * (delta / max(0.3, width)) ** 2)


def demand_series(demand, slots, slot_seconds):
    if slots <= 0:
        return []
    mean = float(demand.rate_bps)
    name = getattr(demand, 'pattern', 'constant')
    if name == 'constant':
        return [mean] * slots
    centre = float(getattr(demand, 'peak_hour', 14.))
    width = float(getattr(demand, 'peak_width_hours', 3.))
    values = []
    for t in range(slots):
        hour = ((t + 0.5) * slot_seconds / 3600.) % 24.
        bell = _periodic_gaussian(hour, centre, width)
        if name == 'dual_peak':
            secondary = float(getattr(demand, 'second_peak_hour', 21.))
            ratio = float(getattr(demand, 'second_peak_ratio_pct', 65.)) / 100.
            bell += ratio * _periodic_gaussian(hour, secondary, width)
        elif name == 'bursty':
            interval = float(getattr(demand, 'burst_interval_hours', 6.))
            length = float(getattr(demand, 'burst_duration_minutes', 45.)) / 60.
            bell = 1. if (((t + 0.5) * slot_seconds / 3600. - centre) % interval) < length else 0.
        values.append(bell)
    avg = sum(values) / slots
    maximum = max(values)
    uplift = float(getattr(demand, 'peak_uplift_pct', 70.)) / 100.
    spread = maximum - avg
    if spread < 1e-12 or uplift == 0:
        return [mean] * slots
    raw = [max(0., 1. + uplift * (v - avg) / spread) for v in values]
    renorm = sum(raw) / slots
    return [mean * v / renorm for v in raw]


def demand_rates(scenario, slots, seconds):
    return {d.id: demand_series(d, slots, seconds) for d in scenario.demands}
