"""Deterministic timed manual weather overlays (no synthetic SKR fallback).

A schedule makes the input visibility/rate time-dependent before the existing
weather_physics attenuation fit. This is a constructed front, not ERA5.
"""
from __future__ import annotations


def weather_at(region, second):
    start = float(region.active_from_seconds)
    finish = float(region.active_until_seconds) if region.active_until_seconds is not None else float('inf')
    second = float(second)
    if second < start or second >= finish:
        return None
    if finish <= start:
        return None
    ramp = min(float(region.ramp_seconds), max(0., (finish-start)/2.))
    strength = 1.0
    if ramp > 0:
        strength = min(1., (second-start)/ramp, (finish-second)/ramp)
    strength = max(0., min(1., strength * float(region.intensity_fraction)))
    if strength <= 0:
        return None
    now = region.model_copy(deep=True)
    now.lat = max(-90., min(90., region.lat + region.drift_lat_deg_per_hour * second/3600.))
    now.lon = ((region.lon + region.drift_lon_deg_per_hour * second/3600. + 180.) % 360.) - 180.
    now.intensity_fraction = strength
    now.attenuation_db *= strength
    if region.effect == 'fog' and region.visibility_km is not None:
        # Blend optical extinction (inverse visibility) rather than visibility.
        now.visibility_km = 1. / ((1-strength)/100. + strength/region.visibility_km)
    elif region.precipitation_rate_mm_h is not None:
        now.precipitation_rate_mm_h = region.precipitation_rate_mm_h * strength
    return now
