"""Numerical-model tests run the ORIGINAL upstream channel formula, with
only the separately-tested native LOWTRAN wrapper mocked in this CI environment.
The production backend never substitutes atmospheric estimates.
"""
import pytest

@pytest.fixture(autouse=True)
def upstream_with_fixed_test_atmosphere(tmp_path, monkeypatch):
    from stratoq_demo import real_rates
    from balloon_qnet import transmittance
    monkeypatch.setattr(real_rates,'CACHE_PATH',tmp_path/'channel.sqlite3')
    monkeypatch.setattr(transmittance,'slant',lambda *args,**kw:0.82)
