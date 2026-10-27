"""Weather-specific attenuation overlay on the unmodified Balloon-QNet clear-sky eta.

Uses helper.py's baseline extinction coefficients (fog 3.91/V, rain 2.8/V,
snow 58/V). User rain/snow rates are mapped to visibility via an explicitly
heuristic power law; the source helper has NO mm/h conversion. For comparison,
5 mm/h rain and 2 mm/h water-equivalent snow correspond to V=4 km.
This is NOT a validated precipitation microphysics model.
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
        visibility=max(0.01,float(getattr(weather,'visibility_km',0.5)))
        q=1.6 if visibility>50 else 1.3 if visibility>6 else 0.585*visibility**(1/3)
        # Helper.py uses a Kim/Kruse-like visibility dependence; 1550 nm.
        gamma=3.91/visibility*(1550/550)**(-q)
    else:
        rate=max(0.,float(getattr(weather,'precipitation_rate_mm_h',5.0)))
        if rate==0:gamma=0.
        else:
            reference=5.0 if effect=='rain' else 2.0
            # Source helper assumes V=4 km. Visibility vs precipitation
            # is NOT specified there: expose this approximate scaling.
            power=0.67 if effect=='rain' else 0.8
            gamma=(2.8 if effect=='rain' else 58.)/4. * (rate/reference)**power
    extra=max(0.,float(getattr(weather,'attenuation_db',0)))
    return gamma*length+extra
