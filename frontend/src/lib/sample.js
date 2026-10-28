export const INITIAL_SCENARIO = {
  ground_stations: [
    { id: 'gs-1', name: 'Timmins', lat: 48.4758, lon: -81.3305, capacity_bits: 8000000, n_rx: 1, n_tx: 1, yaw_deg: 0 },
    { id: 'gs-2', name: 'Iroquois Falls', lat: 48.7666, lon: -80.6826, capacity_bits: 8000000, n_rx: 1, n_tx: 1, yaw_deg: 0 },
  ],
  balloons: [
    { id: 'hap-1', name: 'Strato-01', lat: 48.6212, lon: -81.00655,
      altitude_km: 15, coverage_km: 85, capacity_bits:12000000, n_rx:1, n_tx:1, yaw_deg: 18 },
  ],
  weather_regions: [],
  link_overrides: [],
  demands: [{ id: 'd-1', source: 'gs-1', target: 'gs-2', rate_bps: 4000 }],
  config: { slots: 288, slot_seconds: 300, base_rate_bps: 36000, allocation_mode:"scar_q", allocator_seed:42, mcr_samples:3, optical: { wavelength_nm:1550, beam_waist_m:0.15, rx_aperture_down_m:0.75, rx_aperture_up_m:0.40, obscuration_ratio:0.3, cn0:1e-13, pointing_error_rad:1e-7, tracking_efficiency:0.85, detector_efficiency:0.85, ao_correction_order:5, source_rate_hz:80e6, source_efficiency:0.01, qber:0.04 } },
};
