#!/usr/bin/env python3
"""OpenStreetMap fetch + normalize for the Caddie generator.

One course in -> the pack format generate.py consumes. Data is fetched from
the free Overpass API (© OpenStreetMap contributors, ODbL — keep the
attribution line in anything user-facing). Be polite: this module sleeps
between calls and identifies itself; run big sweeps sharded by market.
"""
import json, math, time, urllib.request, urllib.parse

MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
UA = 'YoinkCaddie/1.0 (course yardage packs; contact: anthony@amg-demolition.com)'

TYPE_CODE = {'fairway': None, 'green': 'g', 'bunker': 'b', 'tee': 't',
             'water_hazard': 'w', 'lateral_water_hazard': 'w',
             'penalty_area': 'w'}   # post-2019 tagging — newer courses use this


def _dp(pts, eps):
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]; bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    idx, mx = 0, 0.0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs((px - ax) * dy - (py - ay) * dx) / n if n else math.hypot(px - ax, py - ay)
        if d > mx:
            mx, idx = d, i
    if mx > eps:
        l = _dp(pts[:idx + 1], eps); r = _dp(pts[idx:], eps)
        return l[:-1] + r
    return [pts[0], pts[-1]]


def overpass(query, mirror=0, timeout=90):
    body = 'data=' + urllib.parse.quote(query)
    req = urllib.request.Request(MIRRORS[mirror % len(MIRRORS)],
                                 data=body.encode(),
                                 headers={'Content-Type': 'application/x-www-form-urlencoded',
                                          'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _try_overpass(query, tries=3, base_mirror=0):
    last = None
    for i in range(tries):
        try:
            return overpass(query, base_mirror + i)
        except Exception as e:
            last = e
            time.sleep(6 * (i + 1))
    raise last


def fetch_course(key, name, market, lat, lng, pad=0.020, mirror=0):
    """Fetch one course's features in TWO queries: golf (required) and
    context (water + wood, best-effort). One combined query blows Overpass's
    memory near dense multi-course sites like Bethpage."""
    bb = f'{lat - pad},{lng - pad},{lat + pad},{lng + pad}'
    # only the types we render — fairway/rough geometry is huge and unused
    qg = (f'[out:json][timeout:60];'
          f'way["golf"~"^(hole|green|bunker|tee|water_hazard|lateral_water_hazard|penalty_area)$"]({bb});'
          f'out tags geom;')
    jg = _try_overpass(qg, base_mirror=mirror)   # required — raises on failure
    holes, feats = [], []
    for e in jg.get('elements', []):
        if not e.get('geometry'):
            continue
        tags = e.get('tags', {})
        golf = tags.get('golf')
        if golf == 'hole':
            holes.append({'r': tags.get('ref', '?'), 'p': tags.get('par', ''),
                          'n': tags.get('name', ''),
                          'l': [[round(g['lat'], 5), round(g['lon'], 5)] for g in e['geometry']]})
            continue
        t = TYPE_CODE.get(golf)
        if not t:
            continue
        g = _dp([[round(p['lat'], 5), round(p['lon'], 5)] for p in e['geometry']], 0.00004)
        if len(g) >= (3 if t != 't' else 2):
            feats.append([t, g])
    # fairways: fetched alone (bundling them with everything else is what blew
    # Overpass's memory at multi-course sites). Best-effort — packs without
    # fairway extents just render the corridor the old way.
    time.sleep(1.0)
    qf = f'[out:json][timeout:60];way["golf"="fairway"]({bb});out geom;'
    try:
        jf = _try_overpass(qf, tries=2, base_mirror=mirror)
        for e in jf.get('elements', []):
            if not e.get('geometry') or len(e['geometry']) < 4:
                continue
            g = _dp([[round(p['lat'], 5), round(p['lon'], 5)] for p in e['geometry']], 0.00008)
            if len(g) >= 4:
                feats.append(['F', g])
    except Exception:
        pass  # corridor-only render is still a good render
    # context: water + timber. Best-effort — a course without it still ships.
    time.sleep(1.0)
    pc = pad * 0.8
    bc = f'{lat - pc},{lng - pc},{lat + pc},{lng + pc}'
    qc = (f'[out:json][timeout:60];('
          f'way["natural"="water"]({bc});way["waterway"="riverbank"]({bc});'
          f'way["natural"="wood"]({bc});way["landuse"="forest"]({bc}););out geom;')
    try:
        jc = _try_overpass(qc, tries=2, base_mirror=mirror)
        nw = nx = 0
        for e in jc.get('elements', []):
            if not e.get('geometry') or len(e['geometry']) < 4:
                continue
            tags = e.get('tags', {}) or {}
            is_wood = tags.get('natural') == 'wood' or tags.get('landuse') == 'forest'
            t = 'x' if is_wood else 'w'
            eps = 0.00012 if is_wood else 0.00004
            if t == 'x' and nx >= 80:
                continue
            if t == 'w' and nw >= 120:
                continue
            g = _dp([[round(p['lat'], 5), round(p['lon'], 5)] for p in e['geometry']], eps)
            if len(g) >= 4:
                feats.append([t, g])
                if is_wood: nx += 1
                else: nw += 1
    except Exception:
        pass  # golf-only pack is still a good pack
    # hazards & landmarks: streams, rock, hedges/walls, cart paths, buildings,
    # specimen trees. Best-effort, tightly capped — a course without them is
    # simply a course without them.
    time.sleep(1.0)
    qh = (f'[out:json][timeout:60];('
          f'way["waterway"~"^(stream|ditch)$"]({bc});'
          f'way["natural"~"^(bare_rock|scree|stone)$"]({bc});'
          f'way["barrier"~"^(hedge|wall|fence)$"]({bc});'
          f'way["highway"~"^(path|track)$"]({bc});'
          f'way["building"]({bc});'
          f'node["natural"="tree"]({bc});'
          f');out geom;')
    try:
        jh = _try_overpass(qh, tries=2, base_mirror=mirror)
        caps = {'S': 40, 'r': 40, 'h': 40, 'n': 60, 'p': 80, 'u': 60, 'T': 120}
        cnt = {k: 0 for k in caps}
        for e in jh.get('elements', []):
            tags = e.get('tags', {}) or {}
            if e.get('type') == 'node':
                if tags.get('natural') == 'tree' and cnt['T'] < caps['T']:
                    feats.append(['T', [[round(e['lat'], 5), round(e['lon'], 5)]]])
                    cnt['T'] += 1
                continue
            if not e.get('geometry') or len(e['geometry']) < 2:
                continue
            if tags.get('waterway') in ('stream', 'ditch'):
                t, eps = 'S', 0.00006
            elif tags.get('natural') in ('bare_rock', 'scree', 'stone'):
                t, eps = 'r', 0.00006
            elif tags.get('barrier') == 'hedge':
                t, eps = 'h', 0.0001
            elif tags.get('barrier') in ('wall', 'fence'):
                t, eps = 'n', 0.0001     # built barriers draw as post-and-rail
            elif tags.get('highway') in ('path', 'track'):
                t, eps = 'p', 0.0001
            elif 'building' in tags:
                t, eps = 'u', 0.0001
            else:
                continue
            if cnt[t] >= caps[t]:
                continue
            g = _dp([[round(pp['lat'], 5), round(pp['lon'], 5)] for pp in e['geometry']], eps)
            if len(g) >= 2:
                feats.append([t, g])
                cnt[t] += 1
    except Exception:
        pass  # hazards are a bonus, never a blocker
    return {'c': {'k': key, 'n': name, 'm': market}, 'h': holes, 'f': feats}


def coverage_probe(lat, lng, pad=0.018, mirror=0):
    """Cheap pre-check: counts only, no geometry."""
    bb = f'{lat - pad},{lng - pad},{lat + pad},{lng + pad}'
    q = f'[out:json][timeout:30];(way["golf"="hole"]({bb});way["golf"="green"]({bb}););out tags;'
    j = overpass(q, mirror)
    n = {'hole': 0, 'green': 0}
    for e in j.get('elements', []):
        k = e.get('tags', {}).get('golf')
        if k in n:
            n[k] += 1
    return n
