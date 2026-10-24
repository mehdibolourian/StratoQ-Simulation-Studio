"""Streaming CSV/XLSX trajectory importer, time-indexed in-memory registry.

Upload is per HAP. Values are sampled with linear interpolation on the chosen
simulation time grid; original timestamps are in seconds from trajectory start.
Excel `alt` and CSV `Altitude_m` are treated as metres (not kilometres).
"""
import bisect
import csv
import io
import math
import uuid
import xml.etree.ElementTree as ET
from zipfile import ZipFile

TRAJECTORIES = {}
MAX_ROWS = 500_000


def longitude(v):
    return ((float(v) + 180.0) % 360.0) - 180.0


def _excel_rows(contents):
    with ZipFile(io.BytesIO(contents)) as z:
        filename = next((n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')), None)
        if not filename:
            raise ValueError('No worksheet found')
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as fh:
                for _, element in ET.iterparse(fh, events=('end',)):
                    if element.tag.endswith('}si'):
                        strings.append(''.join(e.text or '' for e in element.iter() if e.tag.endswith('}t')))
                        element.clear()
        with z.open(filename) as fh:
            for _, elem in ET.iterparse(fh, events=('end',)):
                if not elem.tag.endswith('}row'):
                    continue
                cells = {}
                for cell in elem:
                    if not cell.tag.endswith('}c'):
                        continue
                    ref = cell.attrib.get('r', '')
                    col = ''.join(x for x in ref if x.isalpha())
                    value = cell.find('{*}v')
                    inline = cell.find('{*}is')
                    if value is not None and value.text is not None:
                        text = strings[int(value.text)] if cell.attrib.get('t') == 's' else value.text
                    elif inline is not None:
                        text = ''.join(n.text or '' for n in inline.iter() if n.tag.endswith('}t'))
                    else:
                        text = None
                    if text is not None:
                        cells[col] = text
                elem.clear()
                if cells:
                    yield cells


def parse_trajectory(filename, contents):
    if filename.lower().endswith('.csv'):
        reader = csv.DictReader(io.TextIOWrapper(io.BytesIO(contents), encoding='utf-8-sig'))
        def unpack(row):
            return (row.get('Time_s'), row.get('Latitude_deg'), row.get('Longitude_deg'), row.get('Altitude_m'))
        rows = (unpack(r) for r in reader)
    elif filename.lower().endswith('.xlsx'):
        it = iter(_excel_rows(contents))
        header = next(it)
        names = {col: str(val).strip().lower() for col,val in header.items()}
        def unpack(row):
            fields = {names[c]: v for c,v in row.items() if c in names}
            return fields.get('time_s'), fields.get('lat'), fields.get('lon'), fields.get('alt')
        rows = (unpack(r) for r in it)
    else:
        raise ValueError('Upload a .csv or .xlsx file')
    times, latitudes, longitudes, altitudes = [], [], [], []
    for values in rows:
        try:
            t,lat,lon,alt = (float(v) for v in values)
        except (TypeError, ValueError):
            continue
        if not all(map(math.isfinite, (t,lat,lon,alt))) or t < 0 or not -90<=lat<=90 or alt<0:
            continue
        if times and t <= times[-1]:
            continue  # Solver duplicate/rejected time steps
        times.append(t)
        latitudes.append(lat)
        longitudes.append(longitude(lon))
        altitudes.append(alt / 1000.0)
        if len(times) > MAX_ROWS:
            raise ValueError('Too many trajectory samples')
    if len(times) < 2 or times[-1] <= times[0]:
        raise ValueError('Need at least two distinct increasing timestamps')
    if min(altitudes) < 0 or max(altitudes)>100:
        raise ValueError('Altitude must be between 0 and 100 km after metre conversion')
    return dict(times=times, lats=latitudes, lons=longitudes, alts=altitudes, duration_seconds=times[-1], rows=len(times))


def register(filename, contents):
    trajectory = parse_trajectory(filename, contents)
    key = uuid.uuid4().hex
    TRAJECTORIES[key] = trajectory
    return {'trajectory_id':key, 'filename':filename, 'duration_seconds':trajectory['duration_seconds'], 'rows':trajectory['rows'], 'first':sample(key, 0), 'last':sample(key, trajectory['duration_seconds'])}


def sample(key, second):
    data=TRAJECTORIES.get(key)
    if data is None:
        raise ValueError('Uploaded trajectory is no longer available; please upload it again')
    t=data['times']
    second=min(max(float(second),t[0]),t[-1])
    j=bisect.bisect_right(t,second)
    if j == 0: i=0; j=0
    elif j == len(t): i=len(t)-1; j=i
    else: i=j-1
    ratio=(second-t[i])/(t[j]-t[i]) if i!=j else 0
    def interp(key):return data[key][i] + ratio*(data[key][j]-data[key][i])
    # Avoid interpolating across the international dateline
    lon0,lon1=data['lons'][i],data['lons'][j]
    delta=((lon1-lon0+180)%360)-180
    return {'lat':interp('lats'),'lon':longitude(lon0+ratio*delta),'altitude_km':interp('alts')}


def horizon_seconds(scenario):
    ids=[b.trajectory_id for b in scenario.balloons if b.trajectory_id]
    if not ids:return None
    if any(k not in TRAJECTORIES for k in ids):
        raise ValueError('Trajectory session expired; re-upload the file')
    return min(TRAJECTORIES[k]['duration_seconds'] for k in ids)


def scenario_at(scenario, seconds):
    updated=scenario.model_copy(deep=True)
    positions={}
    for balloon in updated.balloons:
        if balloon.trajectory_id:
            point=sample(balloon.trajectory_id,seconds)
            balloon.lat=point['lat']; balloon.lon=point['lon']; balloon.altitude_km=max(0.001, point['altitude_km'])
        positions[balloon.id]={'lat':balloon.lat,'lon':balloon.lon,'altitude_km':balloon.altitude_km}
    return updated,positions
