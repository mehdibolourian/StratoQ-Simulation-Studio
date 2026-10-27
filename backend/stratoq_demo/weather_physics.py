"""Weather-specific attenuation overlay on the unmodified Balloon-QNet clear-sky eta.

Fog uses helper.py's 3.91/V visibility-based expression. Rain uses the
ITU-R F.2106-1 1.076*R^.67 specific attenuation. Snow uses 2024 published
wet/dry optical FSO rate laws. Snow wet/dry is an explicit manual choice; for
ERA5 a temperature proxy selects it. These fits have known limitations and
are not full microphysical scattering calculations.
"""
from __future__ import annotations
import math


def _xy(lat, lon, lat0, lon0):
    return ((lon-lon0)*111.32*math.cos(math.radians(lat0)), (lat-lat0)*111.32)


def _intersect_intervals(gs, hap, weather):
    """Intervals in t along GS→HAP slant ray inside footprint and weather layer."""
    lat0=weather.lat
    gx,gy=_xy(gs.lat, gs.lon,lat0,weather.lon)
    hx,hy=_xy(hap.lat,hap.lon,lat0,weather.lon)
    dx,dy=hx-gx,hy-gy
    a=dx*dx+dy*dy
    if a<1e-12:
        if gx*gx+gy*gy>weather.radius_km**2: return 0.,0.
        circle_lo,circle_hi=0.,1.
    else:
        b=2*(gx*dx+gy*dy)
        c=gx*gx+gy*gy-weather.radius_km**2
        discriminant=b*b-4*a*c
        if discriminant<0: return 0.,0.
        root=math.sqrt(max(discriminant,0))
        circle_lo=max(0.,(-b-root)/(2*a))
        circle_hi=min(1.,(-b+root)/(2*a))
        if circle_hi<=circle_lo:return 0.,0.
    elevation=math.degrees(math.atan2(hap.altitude_km,math.sqrt(a)))
    return circle_lo,circle_hi


def extinction_db_per_km(effect, visibility_km=None, precipitation_rate_mm_h=None,
                         wavelength_nm=1550., snow_type='wet'):
    """Empirical optical specific attenuation in dB/km (see V10 documentation)."""
    if effect == 'fog':
        v=max(.01,float(visibility_km if visibility_km is not None else .5))
        q=1.6 if v>50 else 1.3 if v>6 else .585*v**(1./3.)
        return 3.91/v*(wavelength_nm/550.)**(-q)
    r=max(0.,float(precipitation_rate_mm_h or 0.))
    if not r:return 0.
    if effect == 'rain':return 1.076*r**.67 # ITU-R F.2106-1
    if effect == 'snow':
        if snow_type=='wet':return (0.0001023*wavelength_nm+3.79)*r**.72
        if snow_type=='dry':return (0.0000542*wavelength_nm+5.50)*r**1.38
        raise ValueError('Snow wet/dry classification required')
    raise ValueError('Unknown weather type: '+str(effect))


def regional_weather_loss_db(gs, hap, weather):
    """Attenuation in dB for the ray portion in the weather cylinder.

    Optional attenuation_db is an additional total path loss (only if the
    ground projection intersects), preserving the previous UI override.
    """
    lo,hi=_intersect_intervals(gs,hap,weather)
    if hi<=lo:return 0.
    effect=getattr(weather,'effect','fog')
    # Backward compatibility: older regions only specified an extra dB loss.
    intensity = (getattr(weather,'visibility_km',None) if effect=='fog'
                 else getattr(weather,'precipitation_rate_mm_h',None))
    if intensity is None:
        return max(0.,float(getattr(weather,'attenuation_db',0)))
    ceiling=0.5 if effect=='fog' else 5.0  # km: original StratoQ H_C, H_W
    # Beam height z(t) = altitude * t; truncate to weather-layer height.
    hi=min(hi,ceiling/max(hap.altitude_km,1e-9))
    length=math.hypot(math.hypot(
        (hap.lon-gs.lon)*111.32*math.cos(math.radians((hap.lat+gs.lat)/2)),
        (hap.lat-gs.lat)*111.32), hap.altitude_km)*max(0.,hi-lo)
    if effect=='fog':
        gamma=extinction_db_per_km('fog',visibility_km=getattr(weather,'visibility_km',None))
    else:
        gamma=extinction_db_per_km(effect,precipitation_rate_mm_h=getattr(weather,'precipitation_rate_mm_h',None),snow_type=getattr(weather,'snow_type','wet'))
    extra=max(0.,float(getattr(weather,'attenuation_db',0)))
    return gamma*length+extra
