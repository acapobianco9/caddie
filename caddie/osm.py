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


def _dry(tags):
    """True when OSM itself says this water is not there most of the year.

    A dry wash drawn as a lake is not a style bug, it is a false statement
    about where the ball ends up. Angeles National plays across the Tujunga
    Wash; we drew the wash as a 722-yard lake for months because we read the
    polygon and ignored the tag sitting on it (Aug 2026).
    """
    return (tags.get('intermittent') in ('yes', 'seasonal')
            or tags.get('seasonal') in ('yes', 'dry', 'spring', 'summer')
            or tags.get('water') in ('intermittent', 'wadi')
            or tags.get('waterway') == 'wadi'
            or tags.get('basin') in ('detention', 'infiltration'))


def _wet(tags):
    """True only when the survey says there is actually water in this thing.

    Post-2019 tagging files desert scrub, native area and dry wash under
    golf=penalty_area, and TYPE_CODE was painting every one of them blue.
    That — not the intermittent wash — is what made Angeles National look like
    a water park: seven scrub penalty areas, one of them 603 yards long.
    """
    return bool(tags.get('natural') == 'water' or tags.get('water')
                or tags.get('waterway') or tags.get('landuse') == 'reservoir')


def _clip(pts, la0, lo0, la1, lo1):
    """The longest run of a way that lies inside the box, plus one point
    either side so the line leaves the frame instead of stopping short.

    Overpass returns a way's WHOLE geometry when any part of it touches the
    bbox, and a coastline or clifftop can run for miles. Without this a
    seaside hole carries the entire county's shoreline in its pack.
    """
    inb = [la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1 for p in pts]
    best, run = (0, 0), None
    for i, ok in enumerate(inb):
        if ok and run is None:
            run = i
        elif not ok and run is not None:
            if i - run > best[1] - best[0]:
                best = (run, i)
            run = None
    if run is not None and len(inb) - run > best[1] - best[0]:
        best = (run, len(inb))
    a = max(0, best[0] - 1); b = min(len(pts), best[1] + 1)
    return pts[a:b] if b - a >= 2 else []


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
        # a penalty area with no water in it is ground you take a stroke in,
        # not water you carry. It still matters; it just isn't blue.
        if t == 'w' and (not _wet(tags) or _dry(tags)):
            t = 'P'
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
    # tree rows come back with the woodland. A golf course is far more often
    # mapped as rows and individual trees than as a wood polygon — reading
    # only polygons is what starved the honest tree rule (GEN 6, Aug 24 2026).
    # GEN 7 widens this to the ground the hole actually sits on: the coastline,
    # the beach and dune sand, the saltmarsh, the clifftop — and, separately,
    # the water OSM tells us is dry most of the year.
    qc = (f'[out:json][timeout:60];('
          f'way["natural"="water"]({bc});way["waterway"="riverbank"]({bc});'
          f'way["natural"="wood"]({bc});way["landuse"="forest"]({bc});'
          f'way["natural"="tree_row"]({bc});'
          f'way["natural"="coastline"]({bc});'
          f'way["natural"~"^(beach|sand|dune|shingle)$"]({bc});'
          f'way["natural"="wetland"]({bc});'
          f'way["natural"="cliff"]({bc});'
          f');out tags geom;')
    try:
        jc = _try_overpass(qc, tries=2, base_mirror=mirror)
        #   w water   x wood   X tree row   i water that is dry most of the year
        #   C coastline (mean high water)   A sand: beach, dune, waste
        #   M wetland / saltmarsh           L clifftop
        caps = {'w': 120, 'x': 80, 'X': 60, 'i': 30,
                'C': 10, 'A': 40, 'M': 30, 'L': 20}
        cnt = {k: 0 for k in caps}
        la0, lo0 = lat - pc * 1.25, lng - pc * 1.25
        la1, lo1 = lat + pc * 1.25, lng + pc * 1.25
        for e in jc.get('elements', []):
            if not e.get('geometry'):
                continue
            tags = e.get('tags', {}) or {}
            # A course pond is nearly always tagged BOTH golf=water_hazard and
            # natural=water, and a course bunker BOTH golf=bunker and
            # natural=sand. Those already came back correctly typed from the
            # golf query; taking them again here is what double-drew the water
            # and would have painted 55 phantom waste areas over Angeles
            # National's bunkers.
            if tags.get('golf') in TYPE_CODE or tags.get('golf') in ('hole', 'fairway'):
                continue
            nat = tags.get('natural')
            if nat == 'tree_row':
                t, eps, minpts = 'X', 0.00008, 2
            elif nat == 'wood' or tags.get('landuse') == 'forest':
                t, eps, minpts = 'x', 0.00012, 4
            elif nat == 'coastline':
                t, eps, minpts = 'C', 0.00006, 2
            elif nat == 'cliff':
                t, eps, minpts = 'L', 0.00006, 2
            elif nat == 'wetland':
                t, eps, minpts = 'M', 0.0001, 4
            elif nat in ('beach', 'sand', 'dune', 'shingle'):
                t, eps, minpts = 'A', 0.00008, 4
            elif _dry(tags):
                t, eps, minpts = 'i', 0.00006, 4
            else:
                t, eps, minpts = 'w', 0.00004, 4
            if len(e['geometry']) < minpts or cnt[t] >= caps[t]:
                continue
            raw = [[round(p['lat'], 5), round(p['lon'], 5)] for p in e['geometry']]
            if t in ('C', 'L'):
                raw = _clip(raw, la0, lo0, la1, lo1)
            g = _dp(raw, eps) if len(raw) >= minpts else []
            if len(g) >= minpts:
                feats.append([t, g])
                cnt[t] += 1
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
        # tree NODES are one coordinate each and are the main way a course's
        # timber gets mapped, so they get a generous cap (GEN 6).
        caps = {'S': 40, 'J': 30, 'r': 40, 'h': 40, 'n': 60, 'p': 80, 'u': 60, 'T': 400}
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
                # a wash that runs twice a year is not a stream; it is ground
                t, eps = ('J' if _dry(tags) else 'S'), 0.00006
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
