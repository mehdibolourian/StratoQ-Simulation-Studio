"""Fast NetSquid-free analytical approximation of the supplied balloon_qnet BB84 model.

Defaults follow `transmittance_simulation.py` (1550 nm, W0=.15 m,
D_RX=.75/.40 m, 80 MHz source, source efficiency=.01, QBER=.04).

This is a reduced Gaussian-beam/atmospheric/turbulence approximation, NOT the
original NetSquid-backed theoretical channel or StratoQ's missing
`calculate_key_rate_mac`. Do not use these numbers as validated paper results.
"""
import math
from functools import lru_cache

EARTH_KM = 6371.0088

def geometry(gs_lat, gs_lon, hap_lat, hap_lon, hap_alt_km, gs_alt_km=0.):
    """Spherical-Earth ECEF slant range and GS elevation (degrees)."""
    a, b = math.radians(gs_lat), math.radians(hap_lat)
    dl = math.radians(((hap_lon-gs_lon+180) % 360)-180)
    cd = max(-1.,min(1., math.sin(a)*math.sin(b)+math.cos(a)*math.cos(b)*math.cos(dl)))
    rg, rh = EARTH_KM+gs_alt_km, EARTH_KM+hap_alt_km
    d = math.sqrt(max(0., (rh-rg)**2 + 2*rg*rh*(1-cd)))
    if d < 1.e-10:
        return 0., 90., 0.
    sin_el = max(-1.,min(1.,(rh*cd-rg)/d))
    return d, math.degrees(math.asin(sin_el)), EARTH_KM*math.acos(cd)

def binary_entropy(p):
    return -p*math.log2(p)-(1-p)*math.log2(1-p) if 0 < p < 1 else 0.

@lru_cache(maxsize=150_000)
def _clear_channel(distance_km, elev_deg, hap_alt_km, direction, params):
    """Only the dry, physical-path part is cached: weather varies per slot."""
    (wavelength_nm, waist_m, down_d, up_d, obscuration,
     cn0, pointing_rad, tracking, detector, n_ao, visibility_km) = params
    if distance_km <= 0 or elev_deg <= 0:
        return 0.0
    lam = wavelength_nm * 1e-9
    L = distance_km * 1000.
    w = waist_m * math.sqrt(1+(lam*L/(math.pi*waist_m*waist_m))**2)
    D = down_d if direction == 'downlink' else up_d
    rx_r = D/2.
    # Gaussian aperture encircled energy (unobstructed beam).
    aperture_eta = -math.expm1(-2*(rx_r/max(1e-12,w))**2)
    aperture_eta *= max(0., 1-obscuration**2)
    # Simplified pointing jitter penalty (Gaussian convolution).
    pointing_eta = w*w/(w*w+4*(pointing_rad*L)**2)
    # Clear-air extinction concentrated in lower ~7 km; near-IR haze term.
    airmass_km = 7*(1-math.exp(-min(hap_alt_km,120.)/7.))/max(0.08, math.sin(math.radians(elev_deg)))
    extinction_db_km = 0.025 + 0.5*4.343*3.912/max(1.,visibility_km)
    atmosphere_eta = 10**(-extinction_db_km*airmass_km/10)
    # Reduced Kolmogorov turbulence coupling proxy. CN2 altitude profile
    # and finite AO are represented approximately, not by the full PDT.
    k = 2*math.pi/lam
    cn2_integral = cn0*1500*(1-math.exp(-hap_alt_km*1000/1500))/max(0.08,math.sin(math.radians(elev_deg)))
    r0 = max(1e-5, (0.423*k*k*max(1e-30,cn2_integral))**(-3/5))
    ao_gain = 8*(1+max(0,n_ao))**1.1
    turbulence_eta = 1/(1 + (D/r0)**(5/3)/ao_gain)
    if direction=='uplink':
        # More uplink beam wander / stronger turbulence at source.
        turbulence_eta *= 0.72
    return min(1., max(0., aperture_eta*pointing_eta*atmosphere_eta*turbulence_eta*tracking*detector))

def analytical_capacity_bps(distance_km, elevation_deg, hap_alt_km, direction,
                            optical, visibility_km=100., weather_loss_db=0.):
    """Asymptotic BB84 secret-key throughput, in bits per second."""
    if elevation_deg <= 0 or distance_km <= 0:
        return 0.
    params=(
        float(optical.wavelength_nm), float(optical.beam_waist_m),
        float(optical.rx_aperture_down_m), float(optical.rx_aperture_up_m),
        float(optical.obscuration_ratio), float(optical.cn0),
        float(optical.pointing_error_rad), float(optical.tracking_efficiency),
        float(optical.detector_efficiency), int(optical.ao_correction_order),
        round(float(visibility_km),2)
    )
    eta=_clear_channel(round(distance_km,3), round(elevation_deg,3),
                       round(hap_alt_km,3), direction, params)
    eta *= 10**(-max(0.,weather_loss_db)/10)
    secret_fraction=max(0.,1-2*binary_entropy(float(optical.qber)))
    return max(0.,float(optical.source_rate_hz)*float(optical.source_efficiency)*eta*secret_fraction)
