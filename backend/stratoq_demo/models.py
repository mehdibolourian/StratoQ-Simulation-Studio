from typing import Literal
from pydantic import BaseModel, Field, model_validator


class GroundStation(BaseModel):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    capacity_bits: float = Field(default=8_000_000, gt=0)
    yaw_deg: float = Field(default=0, ge=-360, le=360)
    n_rx: int = Field(default=1, ge=0, le=10000)
    n_tx: int = Field(default=1, ge=0, le=10000)


class Balloon(BaseModel):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    altitude_km: float = Field(default=15, gt=0, le=50)
    coverage_km: float = Field(default=85, gt=0, le=500)
    capacity_bits: float = Field(default=12_000_000, gt=0)
    yaw_deg: float = Field(default=0, ge=-360, le=360)
    n_rx: int = Field(default=1, ge=0, le=10000)
    n_tx: int = Field(default=1, ge=0, le=10000)
    trajectory_id: str | None = None
    trajectory_name: str | None = None


class Demand(BaseModel):
    id: str
    source: str
    target: str
    rate_bps: float = Field(gt=0, le=1e9)


class WeatherRegion(BaseModel):
    # Canonical weather type. Kept on the validated model so setup.py can
    # access region.effect without an AttributeError.
    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_effect(cls, value):
        if not isinstance(value, dict):
            return value
        value = value.copy()
        if "effect" not in value:
            value["effect"] = value.get("weather_type", value.get("type", "fog"))
        if isinstance(value["effect"], str):
            effect = value["effect"].strip().lower()
            value["effect"] = {"cloud": "fog", "cloud/fog": "fog", "fog/cloud": "fog"}.get(effect, effect)
        return value

    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=17, gt=0, le=500)
    attenuation_db: float = Field(default=3.0, ge=0, le=40)
    effect: Literal["fog", "rain", "snow"] = "fog"


class OpticalParameters(BaseModel):
    # Defaults from balloon_qnet/transmittance_simulation.py (the analytical branch).
    wavelength_nm: float = Field(default=1550, gt=0, le=10000)
    beam_waist_m: float = Field(default=0.15, gt=0, le=10)
    rx_aperture_down_m: float = Field(default=0.75, gt=0, le=20)
    rx_aperture_up_m: float = Field(default=0.40, gt=0, le=20)
    obscuration_ratio: float = Field(default=0.3, ge=0, lt=1)
    cn0: float = Field(default=1e-13, gt=0, le=1e-8)
    pointing_error_rad: float = Field(default=1e-7, ge=0, le=0.1)
    tracking_efficiency: float = Field(default=0.85, ge=0, le=1)
    detector_efficiency: float = Field(default=0.85, ge=0, le=1)
    ao_correction_order: int = Field(default=6, ge=0, le=100)
    wind_speed_mps: float = Field(default=10., gt=0, le=100)
    source_rate_hz: float = Field(default=80e6, gt=0, le=1e12)
    source_efficiency: float = Field(default=0.01, ge=0, le=1)
    qber: float = Field(default=0.04, ge=0, lt=0.5)


class SimulationConfig(BaseModel):
    slots: int = Field(default=24, ge=1, le=1500)
    slot_seconds: int = Field(default=300, ge=1, le=86400)
    base_rate_bps: float = Field(default=36_000, gt=0, le=1e9)  # legacy input, ignored by physical engine
    optical: OpticalParameters = Field(default_factory=OpticalParameters)
    allocation_mode: Literal["random", "greedy"] = "random"
    allocator_seed: int = Field(default=42, ge=0, le=2**31-1)
    channel_workers: int = Field(default=10, ge=1, le=24)


class OpticalLinkOverride(BaseModel):
    source: str
    target: str
    enabled: bool = True
    visibility_km: float = Field(default=100, gt=0, le=500)
    capacity_limit_bps: float | None = Field(default=None, ge=0)


class Scenario(BaseModel):
    ground_stations: list[GroundStation]
    balloons: list[Balloon]
    demands: list[Demand]
    weather_regions: list[WeatherRegion] = Field(default_factory=list)
    config: SimulationConfig = Field(default_factory=SimulationConfig)
    link_overrides: list[OpticalLinkOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        all_ids = [x.id for items in (
            self.ground_stations, self.balloons, self.demands, self.weather_regions
        ) for x in items]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("All object IDs must be unique")
        gs_ids = {x.id for x in self.ground_stations}
        for demand in self.demands:
            if demand.source not in gs_ids or demand.target not in gs_ids:
                raise ValueError(f"Unknown ground station in demand {demand.id}")
            if demand.source == demand.target:
                raise ValueError(f"Demand {demand.id} must have different endpoints")
        hap_ids = {x.id for x in self.balloons}
        pairs = [(o.source, o.target) for o in self.link_overrides]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Duplicate optical link overrides")
        for o in self.link_overrides:
            if o.source not in gs_ids or o.target not in hap_ids:
                raise ValueError(f"Unknown optical link endpoint {o.source}:{o.target}")
        return self


class LinkState(BaseModel):
    id: str
    source: str
    target: str
    distance_km: float
    elevation_deg: float
    capacity_bps: float
    weather_loss_db: float
    visibility_km: float = 100.0
    weather_flags: tuple[int, int, int] = (0, 0, 0)
    capacity_limit_bps: float | None = None
    stored_bits: float
    used_bps: float = 0.0
    active: bool
    enabled: bool = True
    in_range: bool = True


class DemandState(BaseModel):
    id: str
    source: str
    target: str
    requested_bps: float
    served_bps: float
    path: list[str]
    status: Literal["served", "partial", "blocked"]


class QKPState(BaseModel):
    node_id: str
    stored_bits: float
    capacity_bits: float
    fill_fraction: float


class SimulationFrame(BaseModel):
    slot: int
    time_seconds: int
    links: list[LinkState]
    positions: dict[str, dict[str, float]] = Field(default_factory=dict)
    weather_by_hap: dict[str, dict[str, int]] = Field(default_factory=dict)
    demands: list[DemandState]
    qkps: list[QKPState] = Field(default_factory=list)
    stored_bits_total: float
    served_bps_total: float


class SimulationResult(BaseModel):
    engine: str = "balloon-qnet-theoretical"
    frames: list[SimulationFrame]
    summary: dict[str, float | int]
