"""ERA5 hourly *reanalysis*, not a forecast and not sub-hourly observations.

Single-level fields: tp/sf (m water-equivalent accumulated over the PREVIOUS
hour, indexed by END timestamp), t2m/d2m (K), lcc (0..1).
Precipitation is a rate conserved by overlap integration. Instantaneous fields
are interpolated in time. Horizontal interpolation is bilinear on the ERA5 grid.

Fog is a labelled proxy (RH >= .97 and lcc >= .70), NOT an ERA5 visibility
observation. Its assumed visibility (.5 km) follows StratoQ helper.py's H_C/V.
Rain/snow rate -> attenuation uses published FSO empirical power laws;
coefficients and the wet/dry temperature proxy are documented as model assumptions.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from threading import RLock
import hashlib
import io
import json
import math
import os
import tempfile
import zipfile
import numpy as np

try:
    import xarray as xr
except ImportError:  # let manual simulations run when optional deps absent
    xr = None

CACHE_DIR = Path(__file__).resolve().parents[1] / 'data' / 'era5'
MAX_BYTES = 160 * 1024 * 1024
_MAX_CUBES = 5
_CUBES: dict[str, 'ERA5Cube'] = {}
_LOCK = RLock()
# Physical assumptions from uploaded helper.py; not a model for true fog diagnosis.
ASSUMED_FOG_VISIBILITY_KM = .5
FOG_RH_THRESHOLD = .97
FOG_LOW_CLOUD_THRESHOLD = .70
RATE_THRESHOLD = .05  # mm water equivalent / hour; display threshold, not a measurement floor

ALIASES = {
    'tp': ('tp', 'total_precipitation'),
    'sf': ('sf', 'snowfall'),
    't2m': ('t2m', '2m_temperature', '2m temperature'),
    'd2m': ('d2m', '2m_dewpoint_temperature', '2m dewpoint temperature'),
    'lcc': ('lcc', 'low_cloud_cover'),
}


def _date(day: str | date) -> date:
    if isinstance(day, date): return day
    return date.fromisoformat(day)


def _to_seconds(day: date) -> int:
    return int(datetime.combine(day,time(0),timezone.utc).timestamp())


def humidity(t_kelvin, td_kelvin):
    """RH = e_sat(Tdew) / e_sat(T), Magnus water saturation approximation.

    ECMWF documents this ratio; values are clipped to physical [0,1].
    """
    t=np.asarray(t_kelvin,dtype=float)-273.15
    td=np.asarray(td_kelvin,dtype=float)-273.15
    return np.clip(np.exp(17.625*td/(243.04+td)-17.625*t/(243.04+t)),0,1)


def _normalize(ds):
    rename={}
    for name, alternatives in ALIASES.items():
        candidate=next((a for a in alternatives if a in ds.data_vars),None)
        if candidate is None:
            raise ValueError(f'ERA5 NetCDF missing {name} ({", ".join(alternatives)}); no synthetic fallback')
        if candidate!=name:rename[candidate]=name
    ds=ds.rename(rename)
    dim_rename={}
    for canonical, alternatives in [('time',('valid_time','time')),('latitude',('latitude','lat')),('longitude',('longitude','lon'))]:
        hit=next((a for a in alternatives if a in ds.coords or a in ds.dims),None)
        if not hit:raise ValueError(f'ERA5 requires coordinate {canonical}')
        if hit!=canonical:dim_rename[hit]=canonical
    ds=ds.rename(dim_rename)
    for name in ALIASES:
        field=ds[name]
        extras=[d for d in field.dims if d not in ('time','latitude','longitude')]
        for dim in extras:
            if dim=='expver' and field.sizes[dim]>1:
                # ERA5T may split early-release and final values into expver
                # coordinates. Keep the first finite value, never average.
                first=field.isel({dim:0},drop=True)
                for idx in range(1,field.sizes[dim]):
                    first=first.combine_first(field.isel({dim:idx},drop=True))
                field=first
            else:
                if field.sizes[dim]!=1:raise ValueError(f'ERA5 {name} has unsupported dimension {dim}')
                field=field.isel({dim:0},drop=True)
        ds[name]=field.transpose('time','latitude','longitude')
    return ds


@dataclass
class ERA5Cube:
    day: date
    times: np.ndarray
    lats: np.ndarray
    lons: np.ndarray
    arrays: dict[str,np.ndarray]
    dataset_id: str
    filename: str

    @classmethod
    def from_dataset(cls, dataset, day: str | date, dataset_id='test', filename='uploaded.nc'):
        if xr is None:raise RuntimeError('xarray and scipy (or netCDF4) are required for ERA5 NetCDF')
        day=_date(day)
        ds=_normalize(dataset)
        ds=ds.sortby('time').sortby('latitude')
        # Normalize 0..360 longitudes to -180..180 then sort the coordinate.
        ds=ds.assign_coords(longitude=((ds.longitude+180)%360-180)).sortby('longitude')
        times=np.asarray(ds.time.values).astype('datetime64[s]').astype(np.int64)
        lats=np.asarray(ds.latitude.values,dtype=float)
        lons=np.asarray(ds.longitude.values,dtype=float)
        if len(times)<25 or len(lats)<2 or len(lons)<2:
            raise ValueError('ERA5 needs at least 25 hourly timestamps and a 2×2 spatial grid')
        if len(set(times))!=len(times) or np.any(np.diff(times)!=3600):
            raise ValueError('ERA5 timestamps must be unique and consecutive hourly UTC timestamps')
        start=_to_seconds(day)
        if times[0]>start or times[-1]<start+86400:
            raise ValueError('ERA5 data must cover 00:00 UTC of selected date through 00:00 UTC next day, including the latter accumulation')
        if np.any(np.diff(lats)<=0) or np.any(np.diff(lons)<=0):raise ValueError('ERA5 grid must be increasing')
        arrays={}
        for name in ALIASES:
            units=str(ds[name].attrs.get('units','')).strip().lower()
            if name in ('tp','sf') and units not in ('m','m of water equivalent','m water equivalent'):
                raise ValueError(f'ERA5 {name} needs metres of water equivalent, found {units!r}')
            if name in ('t2m','d2m') and units not in ('k','kelvin'):
                raise ValueError(f'ERA5 {name} needs kelvin, found {units!r}')
            if name=='lcc' and units not in ('(0 - 1)','0-1','1','', 'fraction'):
                raise ValueError(f'ERA5 lcc needs fractional cloud cover, found {units!r}')
            a=np.asarray(ds[name].transpose('time','latitude','longitude').values,dtype=np.float64)
            if a.shape!=(len(times),len(lats),len(lons)) or not np.all(np.isfinite(a)):
                raise ValueError(f'ERA5 {name} has missing, non-finite, or inconsistent data')
            if name in ('tp','sf') and np.min(a)<-1e-7:
                raise ValueError('ERA5 accumulated precipitation must not contain negative values')
            arrays[name]=a
        return cls(day,times,lats,lons,arrays,dataset_id,filename)

    @property
    def bounds(self):
        return {'north':float(self.lats[-1]),'south':float(self.lats[0]),
                'west':float(self.lons[0]),'east':float(self.lons[-1])}

    def metadata(self):
        return {'dataset_id':self.dataset_id,'date_utc':self.day.isoformat(),
                'bounds':self.bounds,'grid':[len(self.lats),len(self.lons)],
                'source':('ERA5 via Open-Meteo historical API (grid samples, converted units)'
                          if self.filename.startswith('Open-Meteo ERA5 ') else
                          'CDS ERA5 single levels (retrieved)' if self.filename.startswith('CDS ERA5 ') else
                          'User-supplied ERA5-compatible NetCDF (provenance unverified)'),
                'filename':self.filename,
                'fog_quality':'proxy: RH≥97% and low-cloud cover≥70%; visibility assumed 0.5 km',
                'precipitation_quality':('Open-Meteo hourly precipitation mm converted to m SWE; snowfall cm / 7 to mm SWE (fixed ratio), partitioned into rain and snow'
                                         if self.filename.startswith('Open-Meteo ERA5 ') else
                                         'ERA5 hourly accumulated m water equivalent, partitioned into rain and snow')}

    def validate_area(self, scenario):
        nodes=list(scenario.ground_stations)+list(scenario.balloons)
        from .trajectories import scenario_at, horizon_seconds
        horizon=horizon_seconds(scenario)
        snapshots=[scenario]
        if horizon and scenario.balloons:
            snapshots=[scenario_at(scenario, sec)[0] for sec in range(0,min(86400,int(horizon))+1,3600)]
        b=self.bounds
        for snap in snapshots:
            for n in list(snap.ground_stations)+list(snap.balloons):
                if not(b['south']<=n.lat<=b['north'] and b['west']<=n.lon<=b['east']):
                    raise ValueError(f'ERA5 grid does not cover {n.name} ({n.lat:.3f}, {n.lon:.3f}); reload for the updated topology')

    def _at_time(self, field: str, instant_sec: float):
        times=self.times
        if instant_sec<times[0] or instant_sec>times[-1]:
            raise ValueError('Weather sample outside ERA5 coverage')
        idx=min(max(int(np.searchsorted(times,instant_sec,side='right')-1),0),len(times)-2)
        alpha=(instant_sec-times[idx])/(times[idx+1]-times[idx])
        return (1-alpha)*self.arrays[field][idx]+alpha*self.arrays[field][idx+1]

    def _precip(self,field: str,start: float,end: float):
        """Mean mm/hour over interval. Each ERA5 tp/sf[t] accumulates (t-1h,t]."""
        if not end>start:raise ValueError('Positive sampling duration required')
        if start<self.times[0] or end>self.times[-1]:raise ValueError('ERA5 precipitation outside available hourly intervals')
        weighted=np.zeros((len(self.lats),len(self.lons)),dtype=float)
        for i in range(1,len(self.times)):
            overlap=max(0.,min(end,float(self.times[i]))-max(start,float(self.times[i-1])))
            if overlap:weighted+=self.arrays[field][i]*1000.*(overlap/(end-start))
            if self.times[i]>=end:break
        return weighted  # interval-weighted hourly precipitation rate in mm/h

    def frame(self, start_relative:int, seconds:int):
        # The instance is mutable/unhashable as dataclass: use explicit module cache below.
        return frame_at(self,start_relative,seconds)

    def _bilinear(self,grid,lat,lon):
        if not(self.lats[0]<=lat<=self.lats[-1] and self.lons[0]<=lon<=self.lons[-1]):
            raise ValueError(f'ERA5 grid does not cover ({lat:.4f}, {lon:.4f})')
        j=min(max(int(np.searchsorted(self.lats,lat)-1),0),len(self.lats)-2)
        k=min(max(int(np.searchsorted(self.lons,lon)-1),0),len(self.lons)-2)
        fy=(lat-self.lats[j])/(self.lats[j+1]-self.lats[j])
        fx=(lon-self.lons[k])/(self.lons[k+1]-self.lons[k])
        return float((1-fx)*(1-fy)*grid[j,k]+fx*(1-fy)*grid[j,k+1]+(1-fx)*fy*grid[j+1,k]+fx*fy*grid[j+1,k+1])

    def point(self, frame,lat,lon):
        rh=self._bilinear(frame['rh'],lat,lon)
        cloud=self._bilinear(frame['lcc'],lat,lon)
        return {'rain':self._bilinear(frame['rain'],lat,lon),
                'snow':self._bilinear(frame['snow'],lat,lon),
                't2m_kelvin':self._bilinear(frame['t2m'],lat,lon),
                'fog':rh>=FOG_RH_THRESHOLD and cloud>=FOG_LOW_CLOUD_THRESHOLD,
                'rh':rh,'lcc':cloud}

    def link_attenuation(self,gs,hap,frame, wavelength_nm=1550.):
        """Ray integration of historical attenuation through StratoQ 0–5 km layer.

        Rain/snow rates use the documented v0.9 rate→extinction assumption;
        fog uses StratoQ's helper.py 3.91/V with V=.5 km (proxy).
        """
        from .weather_physics import extinction_db_per_km
        # ITU-R F.2106-1 Annex A: optical rain gamma=1.076 R^0.67 dB/km.
        # 2024 Narvik FSO snow study: wet/dry empirical fits at 1550nm,
        # gamma_wet=3.95 S^0.72, gamma_dry=5.58 S^1.38 dB/km.
        # 2m temperature selects the fit as a *proxy*, not verified snow wetness.
        alt=hap.altitude_km
        if alt<=0:return 0.,(0,0,0)
        slant=math.hypot(math.hypot((hap.lon-gs.lon)*111.32*math.cos(math.radians((hap.lat+gs.lat)/2)),
                                    (hap.lat-gs.lat)*111.32),alt)
        # Mean-value quadrature: 24 slices through 0–5km, 4 sub-slices through 0–0.5km.
        layer_top=min(alt,5.)
        samples=max(12,min(40,int(math.ceil(layer_top/0.25))))
        loss=0.;flags=[0,0,0]
        for n in range(samples):
            z=(n+.5)/samples*layer_top
            f=z/alt
            lat=gs.lat+(hap.lat-gs.lat)*f
            lon=gs.lon+(hap.lon-gs.lon)*f
            wx=self.point(frame,lat,lon)
            segment=(layer_top/samples)*(slant/alt)
            if z<=.5 and wx['fog']:
                loss+=segment*extinction_db_per_km('fog',visibility_km=ASSUMED_FOG_VISIBILITY_KM,wavelength_nm=wavelength_nm)
                flags[0]=1
            for idx,effect in ((1,'rain'),(2,'snow')):
                rate=wx[effect]
                if rate>0:
                    gamma=extinction_db_per_km(effect,
                        precipitation_rate_mm_h=rate,wavelength_nm=wavelength_nm,
                        snow_type=('wet' if wx['t2m_kelvin']>=273.15 else 'dry'))
                    loss+=segment*gamma
                    flags[idx]=1
        return loss,tuple(flags)

    def regions(self, frame, limit=110):
        """Display-only gridded cells. No double-counting in physics.

        Do not send regions into the manual weather overlay. Bilinear ERA5 ray
        integration uses the full raster irrespective of this visual decimation.
        """
        lat_step=float(np.median(np.diff(self.lats)));lon_step=float(np.median(np.diff(self.lons)))
        candidates=[]
        for i,lat in enumerate(self.lats):
            for j,lon in enumerate(self.lons):
                rain=float(frame['rain'][i,j]); snow=float(frame['snow'][i,j]);fog=bool(frame['fog'][i,j])
                radius=.52*math.hypot(111.32*lat_step,111.32*math.cos(math.radians(float(lat)))*lon_step)
                for effect,intensity in (('rain',rain),('snow',snow),('fog',1. if fog else 0.)):
                    if intensity<=(0. if effect=='fog' else RATE_THRESHOLD):continue
                    record={'id':f'era5-{effect}-{i}-{j}', 'name':f'ERA5 {effect} · {lat:.2f}, {lon:.2f}',
                            'effect':effect,'lat':float(lat),'lon':float(lon),'radius_km':round(radius,2),
                            'attenuation_db':0., 'source':'era5','editable':False,
                            'visibility_km':ASSUMED_FOG_VISIBILITY_KM if effect=='fog' else None,
                            'precipitation_rate_mm_h':intensity if effect!='fog' else None}
                    candidates.append((intensity/(5 if effect=='rain' else 2 if effect=='snow' else 1),record))
        candidates.sort(key=lambda x:x[0],reverse=True)
        return [r for _,r in candidates[:limit]]


_FRAME_CACHE={}
_FRAME_LOCK=RLock()
def frame_at(cube,start_relative,seconds):
    key=(cube.dataset_id,int(start_relative),int(seconds))
    with _FRAME_LOCK:
        if key in _FRAME_CACHE:return _FRAME_CACHE[key]
    start=_to_seconds(cube.day)+start_relative
    end=min(_to_seconds(cube.day)+86400,start+seconds)
    if not 0<=start_relative<86400 or end<=start:raise ValueError('Requested slot outside selected UTC day')
    tp=cube._precip('tp',start,end)
    sf=cube._precip('sf',start,end)
    rain=np.maximum(0,tp-sf)
    snow=np.maximum(0,sf)
    mid=(start+end)/2
    rh=humidity(cube._at_time('t2m',mid),cube._at_time('d2m',mid))
    lcc=np.clip(cube._at_time('lcc',mid),0,1)
    f={'rain':rain,'snow':snow,'fog':(rh>=FOG_RH_THRESHOLD)&(lcc>=FOG_LOW_CLOUD_THRESHOLD),
       'rh':rh,'lcc':lcc,'t2m':cube._at_time('t2m',mid)}
    with _FRAME_LOCK:
        if len(_FRAME_CACHE)>64:_FRAME_CACHE.clear()
        _FRAME_CACHE[key]=f
    return f


def _open_bytes(contents:bytes):
    if xr is None:raise RuntimeError('Install xarray and scipy or netCDF4 to decode ERA5')
    if len(contents)>MAX_BYTES:raise ValueError('ERA5 upload exceeds 160 MB')
    with tempfile.TemporaryDirectory(prefix='stratoq-era5-') as tmp:
        path=Path(tmp)/'era5_download'
        path.write_bytes(contents)
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as arc:
                names=[m for m in arc.infolist() if m.filename.lower().endswith(('.nc','.nc4')) and not m.is_dir()]
                if not names:raise ValueError('ERA5 ZIP has no NetCDF files')
                if sum(m.file_size for m in names)>MAX_BYTES*3:raise ValueError('Decompressed ERA5 exceeds size budget')
                datasets=[]
                for i,entry in enumerate(names):
                    out=Path(tmp)/f'era5-{i}.nc'
                    with arc.open(entry) as inp, out.open('wb') as dest:
                        import shutil;shutil.copyfileobj(inp,dest)
                    with xr.open_dataset(out) as ds: datasets.append(ds.load())
                return xr.merge(datasets,compat='override',join='outer')
        out=Path(tmp)/'era5.nc';path.rename(out)
        with xr.open_dataset(out) as ds:return ds.load()


def register_bytes(contents:bytes,day:str|date, filename='uploaded.nc'):
    day=_date(day)
    identity=hashlib.sha256(day.isoformat().encode()+b'\x00'+contents).hexdigest()[:20]
    cube=ERA5Cube.from_dataset(_open_bytes(contents),day,identity,filename)
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    extension='.zip' if zipfile.is_zipfile(io.BytesIO(contents)) else '.nc'
    path=CACHE_DIR/f'{identity}{extension}'
    if not path.exists():path.write_bytes(contents)
    manifest=CACHE_DIR/f'{identity}.json'
    manifest.write_text(json.dumps({'date':day.isoformat(),'filename':filename,'extension':extension}))
    with _LOCK:
        if len(_CUBES)>=_MAX_CUBES:_CUBES.pop(next(iter(_CUBES)))
        _CUBES[identity]=cube
    return cube.metadata()


def get_cube(dataset_id:str|None, day:str|date|None=None):
    if not dataset_id:raise ValueError('Historical ERA5 mode requires a loaded ERA5 dataset')
    with _LOCK:cube=_CUBES.get(dataset_id)
    if cube is None:
        manifest=CACHE_DIR/f'{dataset_id}.json'
        if not manifest.is_file():raise ValueError('ERA5 dataset not found; load ERA5 again (backend may have restarted)')
        metadata=json.loads(manifest.read_text())
        path=CACHE_DIR/f'{dataset_id}{metadata["extension"]}'
        cube=ERA5Cube.from_dataset(_open_bytes(path.read_bytes()),metadata['date'],dataset_id,metadata['filename'])
        with _LOCK:_CUBES[dataset_id]=cube
    if day is not None and cube.day!=_date(day):raise ValueError('Loaded ERA5 dataset date does not match selected historical date')
    return cube


def scenario_era5(scenario):
    if scenario.config.weather_source!='era5':return None
    cube=get_cube(scenario.config.era5_dataset_id,scenario.config.era5_date)
    cube.validate_area(scenario)
    return cube


def roi_from_scenario(scenario, margin=.55):
    from .trajectories import scenario_at, horizon_seconds
    points=[(g.lat,g.lon) for g in scenario.ground_stations]
    horizon=horizon_seconds(scenario)
    seconds=range(0,min(86400,int(horizon))+1,3600) if horizon is not None else [0]
    for sec in seconds:
        snap,_=scenario_at(scenario,sec)
        points +=[(h.lat,h.lon) for h in snap.balloons]
    if not points:raise ValueError('Add at least one GS/HAP before loading weather')
    n=min(90,max(x[0] for x in points)+margin);s=max(-90,min(x[0] for x in points)-margin)
    w=max(-180,min(x[1] for x in points)-margin);e=min(180,max(x[1] for x in points)+margin)
    if n-s>9 or e-w>9:raise ValueError('Topology spans more than 9°; ERA5 automatic request too large. Use a smaller scenario or upload a regional NetCDF.')
    # ERA5 CDS returns regular 0.25° grid; expand to full grid boundaries.
    return [min(90,math.ceil(n*4)/4),max(-180,math.floor(w*4)/4),
            max(-90,math.floor(s*4)/4),min(180,math.ceil(e*4)/4)]
