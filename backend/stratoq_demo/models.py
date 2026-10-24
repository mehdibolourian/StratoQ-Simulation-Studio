from typing import Literal
from pydantic import BaseModel, Field, model_validator


class GroundStation(BaseModel):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    capacity_bits: float = Field(default=8_000_000, gt=0)
    yaw_deg: float = Field(default=0, ge=-360, le=360)


class Balloon(BaseModel):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    altitude_km: float = Field(default=15, gt=0, le=50)
    coverage_km: float = Field(default=85, gt=0, le=500)
    capacity_bits: float = Field(default=12_000_000, gt=0)
    yaw_deg: float = Field(default=0, ge=-360, le=360)
    trajectory_id: str | None = None
    trajectory_name: str | None = None


class Demand(BaseModel):
    id: str
    source: str
    target: str
    rate_bps: float = Field(gt=0, le=1e9)


class WeatherRegion(BaseModel):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=17, gt=0, le=500)
    attenuation_db: float = Field(default=3.0, ge=0, le=40)


class SimulationConfig(BaseModel):
    slots: int = Field(default=24, ge=1, le=1500)
    slot_seconds: int = Field(default=300, ge=1, le=86400)
    base_rate_bps: float = Field(default=36_000, gt=0, le=1e9)


class OpticalLinkOverride(BaseModel):
    source: str
    target: str
    enabled: bool = True


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
    demands: list[DemandState]
    qkps: list[QKPState] = Field(default_factory=list)
    stored_bits_total: float
    served_bps_total: float


class SimulationResult(BaseModel):
    engine: str = "synthetic-demo"
    frames: list[SimulationFrame]
    summary: dict[str, float | int]
