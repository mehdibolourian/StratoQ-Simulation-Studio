from stratoq_demo.models import LinkState


def test_link_state_supports_true_fresh_and_qkp_flow():
    base=dict(id='gs-1:hap-1',source='gs-1',target='hap-1',distance_km=30,
              elevation_deg=45,capacity_bps=4000,weather_loss_db=0,
              stored_bits=2000,used_bps=3500,active=True,activated=True,allocated=True)
    state=LinkState(**base,fresh_used_bps=2000,qkp_used_bps=1500)
    assert state.fresh_used_bps+state.qkp_used_bps == state.used_bps
    assert LinkState(**base).qkp_used_bps == 0.0  # Legacy API backwards compatibility
