#!/usr/bin/env python3
"""Preflight for the *exact interpreter* that will run StratoQ's FastAPI server.

Does not substitute a physics model, change any data, or install packages.
Use --deep to run a real LOWTRAN theoretical-channel calculation.
"""
import argparse
import os
from pathlib import Path
import sys
import sysconfig
import traceback

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
VENV = BACKEND / '.venv'


def check(deep=False, libraries_only=False):
    print(f'Python: {sys.executable}', flush=True)
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError('This bundled macOS LOWTRAN binary needs Python 3.10. Install a Python 3.10 interpreter.')
    if Path(sys.prefix).resolve() != VENV.resolve():
        raise RuntimeError(f'Backend must use its dedicated virtualenv: {VENV}; got prefix {sys.prefix}')
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    import numpy
    import scipy
    from scipy.integrate import quad
    import scipy.integrate._vode  # catches the original macOS Mach-O error
    import scipy.sparse.linalg  # catches PROPACK imports
    from scipy.sparse.linalg._propack import _spropack  # exact new failing extension
    from scipy.special import erf
    for name, package in (('NumPy', numpy), ('SciPy', scipy)):
        p = Path(package.__file__).resolve()
        if not p.is_relative_to(VENV.resolve()):
            raise RuntimeError(f'{name} is loaded from outside backend/.venv: {p}')
        print(f'{name}: {package.__version__} ({p})', flush=True)
    assert abs(quad(lambda x: x*x, 0, 1)[0] - 1/3) < 1e-9
    assert erf(0) == 0
    import fastapi
    import uvicorn
    import xarray
    import pandas
    import netCDF4
    import multipart
    print('FastAPI, Uvicorn, xarray, pandas, NetCDF4 and multipart: OK', flush=True)
    if libraries_only:
        print('PASS: backend Python package imports are healthy.', flush=True)
        return

    from balloon_qnet import transmittance_simulation as ts
    from balloon_qnet.lowtran_piccia.base import import_f2py_mod
    suffix = sysconfig.get_config_var('EXT_SUFFIX')
    native = BACKEND / 'balloon_qnet' / 'lowtran_piccia' / ('lowtran7' + suffix)
    if not native.is_file():
        raise RuntimeError(f'Native LOWTRAN binary missing for this interpreter: {native}; do not substitute an incompatible .so')
    mod = import_f2py_mod('lowtran7')
    if not hasattr(mod, 'lwtrn7'):
        raise RuntimeError('Native LOWTRAN module has no lwtrn7 routine')
    print(f'Balloon-QNet and native LOWTRAN: OK ({native.name})', flush=True)

    import gurobipy as gp
    model = gp.Model('stratoq-preflight')
    model.Params.OutputFlag = 0
    x = model.addVar(lb=0, ub=1)
    model.setObjective(x, gp.GRB.MAXIMIZE)
    model.optimize()
    if model.Status != gp.GRB.OPTIMAL or abs(x.X - 1) > 1e-8:
        raise RuntimeError('Gurobi could not solve a basic optimization; check license and solver installation')
    print(f'Gurobi {gp.gurobi.version()}: valid license and optimization: OK', flush=True)

    if deep:
        import math
        print('Deep check: executing genuine LOWTRAN + balloon_qnet channel theory...', flush=True)
        for direction in ('uplink','downlink'):
            eta = float(ts.channel_theory(direction=direction, gs_alt=0., hap_alt=15.,
                                         distance=27., n_correction=6, params_in=ts.params))
            if not math.isfinite(eta) or not 0 <= eta <= 1:
                raise RuntimeError(f'Invalid {direction} transmittance: {eta}')
            print(f'  {direction}: eta={eta:.8g}', flush=True)
    print('PASS: backend interpreter is ready.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--deep', action='store_true')
    parser.add_argument('--libraries-only', action='store_true')
    args = parser.parse_args()
    try:
        check(deep=args.deep, libraries_only=args.libraries_only)
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        if os.environ.get('STRATOQ_PREFLIGHT_TRACEBACK') == '1':
            traceback.print_exc()
        sys.exit(1)
