"""Run the ACTUAL atmospheric and optical model; never use mock data.

    python verify_physics.py

Success demonstrates that LOWTRAN7 loaded/executed and upstream channel_theory
returned valid efficiencies for both directions. This can take seconds or
compile the native Fortran extension on first run.
"""
from pathlib import Path
import math
import sysconfig
import time

from balloon_qnet import transmittance_simulation as ts
from stratoq_demo.real_rates import PHYSICS_SOURCE_HASH

print('balloon_qnet source fingerprint:',PHYSICS_SOURCE_HASH,flush=True)
print('Native extension suffix:',sysconfig.get_config_var('EXT_SUFFIX'),flush=True)
print('Running real LOWTRAN + AO channel at 15km HAP, 27km slant...',flush=True)
for direction in ('uplink','downlink'):
    start=time.perf_counter()
    eta=ts.channel_theory(direction=direction,gs_alt=0.,hap_alt=15.,
                          distance=27.,n_correction=6,params_in=ts.params)
    assert math.isfinite(float(eta)) and 0 <= eta <= 1, f'Invalid channel {eta}'
    print(f'{direction:8} eta={float(eta):.9g}  SKR={ts.compute_skr(eta):.4f} bit/s  {time.perf_counter()-start:.2f}s',flush=True)
print('PASS: real upstream numerical channel + LOWTRAN7 atmospheric transmittance executed.',flush=True)
