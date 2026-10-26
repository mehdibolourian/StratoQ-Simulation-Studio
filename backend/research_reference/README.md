This is the user-supplied `helper.py`, preserved verbatim for comparison.

Do not import it into the FastAPI server. It wildcard-imports `libraries.py`
which in turn imports Gurobi, NetSquid, graphics and optimization modules;
it also writes a global `K_MAX_checkpoint.pkl` without tracking geometry or
optical-parameter changes, and calls `plt.show()` inside simulation requests.

`stratoq_demo/real_rates.py` adapts its `_compute_key_point` theoretical
branch (the SAME upstream `transmittance_simulation.channel_theory` and the
upstream BB84 `compute_skr` formula), with scenario fingerprints, per-pair
weather attenuation, disk caching and progress callbacks.
