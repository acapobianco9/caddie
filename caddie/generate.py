#!/usr/bin/env python3
"""Yoink Caddie — hole-pack generator.

Takes one course's OSM golf features and emits a JSON "pack" per hole:
real geometry in a hole-local yard frame plus every computed number the
Caddie UI shows (front/mid/back, carries, bends, conifer stands, the read).

The rule the packs serve: the handwriting never touches a number. Every
figure here is computed from surveyed coordinates — nothing is invented.
Where data is missing the pack says so (tier, has_green) instead of guessing.

Input feature dict (see osm.py):
    {"c": {"k": course_key, "n": name, "m": market},
     "h": [{"r": "4", "p": "5", "l": [[lat,lon],...]}, ...],   # hole centerlines
     "f": [["g"|"b"|"t"|"w"|"x", [[lat,lon],...]], ...]}       # polygons
       g green · b bunker · t tee · w water · x wood/timber

Output pack per hole (all coordinates in yards, tee at origin,
hole playing "up" = negative y, matching the phone rendering):
    {"hole","par","tier","yards":{front,mid,back,total},"has_green",
     "line","green","bunkers","waters","tees","woods_used",
     "carries":[{"kind","at"}],"bend":{"at","dir"}|null,
     "stands":[{"side","a0","a1","count"}],"read","sign"}

Tiers: A green+extras · B green only · C centerline only.
"""
import json, math, random, re
import voice

YD_LAT = 121740.0  # yards per degree of latitude


# ---------------- geometry ----------------

def project(pts, lat0, lon0):
    k = math.cos(math.radians(lat0)) * YD_LAT
    return [((p[1] - lon0) * k, -(p[0] - lat0) * YD_LAT) for p in pts]

def rot(pts, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(x * c - y * s, x * s + y * c) for x, y in pts]

def seg_dist(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay), 0.0
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t

def line_dist(p, line):
    best = 1e9; arc = 0; cum = 0
    for i in range(len(line) - 1):
        L = math.hypot(line[i+1][0] - line[i][0], line[i+1][1] - line[i][1])
        d, t = seg_dist(p, line[i], line[i+1])
        if d < best:
            best = d; arc = cum + t * L
        cum += L
    return best, arc

def point_at_arc(line, arc):
    cum = 0
    for i in range(len(line) - 1):
        L = math.hypot(line[i+1][0] - line[i][0], line[i+1][1] - line[i][1])
        if cum + L >= arc:
            t = (arc - cum) / L
            return (line[i][0] + t * (line[i+1][0] - line[i][0]),
                    line[i][1] + t * (line[i+1][1] - line[i][1]))
        cum += L
    return line[-1]

def centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

def area(pts):
    s = 0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2

def arclen(line):
    return sum(math.hypot(line[i+1][0] - line[i][0], line[i+1][1] - line[i][1])
               for i in range(len(line) - 1))

def extend_line(line, extra=80.0):
    (x1, y1), (x2, y2) = line[-2], line[-1]
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    return line[:-1] + [(x2, y2), (x2 + (x2 - x1) / L * extra, y2 + (y2 - y1) / L * extra)]

def pip(pt, poly):
    x, y = pt; inside = False; n = len(poly); j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside

# ---------------- ground: turning survey into the ground you play on ----------------
#
# The corridor is what you play; the ground is what you play it ON. Nothing
# below invents a biome — a hole with no signal stays parkland, which is both
# the honest answer and exactly the old behaviour.

def _resample(pts, n=26):
    """`pts` re-spaced to exactly n points, evenly along its length.

    Both directions matter. crown.py draws one soft wash per shore point, so a
    200-point coastline would cost 200 gradients and look like a caterpillar —
    and a 4-point one would leave gaps of open water between the washes.
    """
    if len(pts) < 2 or n < 2:
        return list(pts)
    seg = [math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1])
           for i in range(len(pts) - 1)]
    L = sum(seg)
    if L <= 0:
        return list(pts[:n])
    out, step, cum, i = [pts[0]], L / (n - 1), 0.0, 0
    for k in range(1, n - 1):
        want = step * k
        while i < len(seg) - 1 and cum + seg[i] < want:
            cum += seg[i]; i += 1
        t = (want - cum) / (seg[i] or 1.0)
        out.append((pts[i][0] + t * (pts[i+1][0] - pts[i][0]),
                    pts[i][1] + t * (pts[i+1][1] - pts[i][1])))
    out.append(pts[-1])
    return out


def _edge_run(poly, line, maxd):
    """The longest run of consecutive vertices of a closed polygon lying
    within maxd of the playing line — the edge of the marsh facing the hole,
    rather than the whole marsh."""
    n = len(poly)
    if n < 3:
        return []
    ok = [line_dist(p, line)[0] <= maxd for p in poly]
    if not any(ok):
        return []
    if all(ok):
        return list(poly)
    best, run = (0, 0), None
    for k in range(2 * n):
        if ok[k % n]:
            if run is None:
                run = k
        else:
            if run is not None and k - run > best[1] - best[0]:
                best = (run, k)
            run = None
    if run is not None and 2 * n - run > best[1] - best[0]:
        best = (run, 2 * n)
    a, b = best[0], min(best[1], best[0] + n)
    return [poly[i % n] for i in range(a, b)] if b - a >= 2 else []


def _buffer(pl, w):
    """A polyline thickened into a polygon, w yards either side. A dry channel
    is a strip of ground, not a line, and the ground layer draws areas."""
    L, R = [], []
    for i in range(len(pl)):
        j = min(i + 1, len(pl) - 1); k = max(i - 1, 0)
        dx = pl[j][0] - pl[k][0]; dy = pl[j][1] - pl[k][1]
        m = math.hypot(dx, dy) or 1.0
        L.append((pl[i][0] - dy / m * w, pl[i][1] + dx / m * w))
        R.append((pl[i][0] + dy / m * w, pl[i][1] - dx / m * w))
    return L + R[::-1]


def water_cross(line, poly, total):
    """Walk the playing line through a water polygon; return (enter, exit) arcs.
    Rivers wander — their bbox lies about carries; the line itself does not."""
    a = 8.0; first = None; last = None
    while a < total:
        if pip(point_at_arc(line, a), poly):
            if first is None:
                first = a
            last = a
        a += 4.0
    return None if first is None else (round(first), round(last + 4.0))


def stream_cross(line, sline, total):
    """Same walk against a LINEAR waterway (stream/ditch): the creek is wet
    for a few yards either side of its centerline."""
    if len(sline) < 2:
        return None
    a = 8.0; first = None; last = None
    while a < total:
        p = point_at_arc(line, a)
        dmin = min(seg_dist(p, sline[i], sline[i+1])[0] for i in range(len(sline) - 1))
        if dmin < 6.0:
            if first is None:
                first = a
            last = a
        a += 4.0
    return None if first is None else (round(first), round(last + 6.0))


def _elev_prof(elev, line_ll, line, total, n=20):
    """Sampled ground line tee->green: feet relative to the tee, n points
    along the playing line. None when the DEM can't cover the hole."""
    if elev is None or len(line) != len(line_ll) or total <= 0 or len(line) < 2:
        return None
    try:
        segs = [math.hypot(line[i+1][0]-line[i][0], line[i+1][1]-line[i][1])
                for i in range(len(line) - 1)]
        out = []
        for k in range(n):
            a = total * k / (n - 1)
            cum = 0.0
            la = lo = None
            for i, L in enumerate(segs):
                if cum + L >= a or i == len(segs) - 1:
                    t = 0.0 if L == 0 else min(1.0, max(0.0, (a - cum) / L))
                    la = line_ll[i][0] + (line_ll[i+1][0]-line_ll[i][0])*t
                    lo = line_ll[i][1] + (line_ll[i+1][1]-line_ll[i][1])*t
                    break
                cum += L
            out.append(elev([la, lo]))
        if sum(1 for v in out if v is None) > 2:
            return None
        for i, v in enumerate(out):
            if v is None:
                out[i] = next((out[j] for j in range(i-1, -1, -1) if out[j] is not None),
                              next((out[j] for j in range(i+1, len(out)) if out[j] is not None), 0.0))
        base = out[0]
        return [int(round((v - base) * 3.28084)) for v in out]
    except Exception:
        return None


def _elev_ft(elev, line_ll):
    """Green-minus-tee elevation in feet from a DEM sampler; None if unknown.
    Negative = downhill. The sampler comes from naip.elevation_sampler."""
    if elev is None:
        return None
    try:
        te = elev(line_ll[0])
        ge = elev(line_ll[-1])
        if te is None or ge is None:
            return None
        d = (ge - te) * 3.28084
        return int(round(d)) if abs(d) < 300 else None
    except Exception:
        return None


def rnd_pts(pts, nd=1):
    return [[round(x, nd), round(y, nd)] for x, y in pts]


# ---------------- per-hole build ----------------

def _miss_cone(arc, total):
    """How far off the playing line a shot can plausibly finish at this point.

    The one gate every optional feature passes through (owner rule, Aug 24
    2026): a thing is drawn only if it exists AND could change how the hole is
    played. Wide through the driver corridor, tighter as the shot shortens in.
    """
    to_green = total - arc
    if to_green < 60:
        return 26.0
    if to_green < 120:
        return 32.0
    return 45.0


def build_hole(hole, feats, woods, seed=0, claim_green=None, elev=None):
    line_ll = hole['l']
    if len(line_ll) < 2:
        return None
    lat0, lon0 = line_ll[0]
    line = project(line_ll, lat0, lon0)
    ang = -math.atan2(line[-1][0] - line[0][0], -(line[-1][1] - line[0][1]))
    line = rot(line, ang)
    total = arclen(line)
    if total < 60 or total > 750:      # not a golf hole
        return None
    try:
        par = int(hole.get('p') or 0)
    except ValueError:
        par = 0
    if par == 0:                        # infer from length when untagged
        par = 3 if total < 245 else (5 if total > 490 else 4)
    xl = extend_line(line, 80)

    keep = []
    wds = []       # woodland polygons
    trows = []     # natural=tree_row lines
    tpts = []      # every mapped natural=tree node, gate or no gate
    fwys = []
    for t, g_ll in feats:
        g = rot(project(g_ll, lat0, lon0), ang)
        if t == 'x':
            wds.append(g); continue
        if t == 'X':
            trows.append(g); continue
        if t == 'F':
            if min(line_dist(p, line)[0] for p in g) < 45:
                fwys.append(g)
            continue
        c = centroid(g); d, arc = line_dist(c, line)
        near = min(line_dist(p, xl)[1] for p in g)
        far = max(line_dist(p, xl)[1] for p in g)
        if t == 't':
            if not (d < 40 and arc < 35): continue
        elif t == 'g':
            if not (d < 45 and arc > total - 55): continue
        elif t in ('b', 'B'):
            if d > 60 or far < 15 or near > total + 22: continue
            # sand abeam of the tee box is another hole's greenside — a real
            # bunker in the first 60 yards would sit on the line, not beside it
            if far < 60 and d > 18: continue
            # same idea, wider net: sand that STARTS inside 90 but sits well
            # off the line is a neighbour's, not a carry (real early carries
            # sit on the line, d small)
            if near < 90 and d > 25: continue
        elif t == 'w':
            dmin = min(line_dist(p, line)[0] for p in g)
            if dmin > 55 or far < 12 or near > total + 15: continue
            d = dmin
        elif t == 'S':      # stream / ditch centerline (linear hazard)
            dmin = min(line_dist(p, line)[0] for p in g)
            if dmin > 60 or far < 10 or near > total + 15: continue
            d = dmin
        elif t == 'r':      # bare rock / scree / stone
            if d > 60 or far < 10 or near > total + 20: continue
        elif t == 'T':      # specimen tree — only if it can catch a shot
            tpts.append(c)   # but EVERY tree counts toward a stand
            if not (d <= _miss_cone(arc, total) and 20 < arc < total + 10):
                continue
        elif t == 'h':      # hedge — only where it can catch a shot
            dmin = min(line_dist(p, line)[0] for p in g)
            amin = min(line_dist(p, line)[1] for p in g)
            if dmin > _miss_cone(amin, total): continue
            d = dmin
        elif t == 'n':      # wall / fence (built barrier)
            dmin = min(line_dist(p, line)[0] for p in g)
            if dmin > 55: continue
            d = dmin
        elif t == 'u':      # building
            if d > 80: continue
        # ---- ground types (GEN 7). These never become hazards or facts; they
        # only decide what colour the ground under the hole is. The gates are
        # wide because ground is context, not a carry.
        elif t == 'i':      # water OSM says is dry most of the year
            d = min(line_dist(p, line)[0] for p in g)
            if d > 110: continue
        elif t == 'J':      # dry channel centreline
            d = min(line_dist(p, line)[0] for p in g)
            if d > 90: continue
        elif t == 'A':      # beach, dune or waste sand
            d = min(line_dist(p, line)[0] for p in g)
            if d > 170: continue
        elif t == 'C':      # coastline (mean high water)
            d = min(line_dist(p, line)[0] for p in g)
            if d > 240: continue
        elif t == 'M':      # wetland / saltmarsh
            d = min(line_dist(p, line)[0] for p in g)
            if d > 190: continue
        elif t == 'L':      # clifftop
            d = min(line_dist(p, line)[0] for p in g)
            if d > 200: continue
        else:
            continue
        keep.append(dict(t=t, g=g, c=c, d=d, arc=arc, near=near, far=far, src=g_ll))
    for wl in (woods or []):
        wds.append(rot(project(wl, lat0, lon0), ang))

    for f in keep:
        if f['t'] == 'w':
            f['cross'] = water_cross(line, f['g'], total)
        elif f['t'] == 'S':
            f['cross'] = stream_cross(line, f['g'], total)

    _wseen = set()
    _dedup = []
    for f in keep:
        if f['t'] == 'w':
            kkey = (round(f['c'][0]), round(f['c'][1]), len(f['g']))
            if kkey in _wseen:
                continue
            _wseen.add(kkey)
        _dedup.append(f)
    keep = _dedup

    greens = [f for f in keep if f['t'] == 'g']
    if len(greens) > 1:
        best = min(greens, key=lambda f: f['d'] + abs(f['arc'] - total))
        keep = [f for f in keep if f['t'] != 'g' or f is best]
        greens = [best]
    # claimed orphan green (course-level pass vetted the distance): the
    # polygon is real survey — only its assignment to this hole is inferred
    if not greens and claim_green is not None:
        g = rot(project(claim_green, lat0, lon0), ang)
        c = centroid(g)
        d, arc = line_dist(c, line)
        f = dict(t='g', g=g, c=c, d=d, arc=arc,
                 near=min(line_dist(p, xl)[1] for p in g),
                 far=max(line_dist(p, xl)[1] for p in g), src=claim_green)
        greens = [f]
        keep.append(f)

    # NAIP sand ('B') backs up the survey, never overrules it: where OSM has
    # real bunkers the imagery adds nothing; where OSM has none, detected
    # sand fills the gap and the pack says so (naip_sand)
    bunkers = [f for f in keep if f['t'] == 'b']
    naip_sand = False
    if not bunkers:
        nb = [f for f in keep if f['t'] == 'B']
        if nb:
            bunkers = nb
            naip_sand = True
    waters = [f for f in keep if f['t'] == 'w']
    streams = [f for f in keep if f['t'] == 'S']
    rocks = [f for f in keep if f['t'] == 'r']
    trees_pt = [f for f in keep if f['t'] == 'T']
    hedges = [f for f in keep if f['t'] == 'h']
    fences = [f for f in keep if f['t'] == 'n']
    bldgs = [f for f in keep if f['t'] == 'u']
    # ---- ground (GEN 7) ----
    drys = [f for f in keep if f['t'] == 'i']
    chans = [f for f in keep if f['t'] == 'J']
    sands = [f for f in keep if f['t'] == 'A']
    coasts = [f for f in keep if f['t'] == 'C']
    wets = [f for f in keep if f['t'] == 'M']
    cliffs = [f for f in keep if f['t'] == 'L']

    def _closest(fs):
        return min((f['d'] for f in fs), default=1e9)

    # one shore polyline: the coastline if there is one, else the clifftop,
    # else the edge of the marsh that actually faces the hole
    shore = []
    if coasts:
        shore = _resample(min(coasts, key=lambda f: f['d'])['g'])
    elif cliffs:
        shore = _resample(min(cliffs, key=lambda f: f['d'])['g'])
    elif wets:
        shore = _resample(_edge_run(min(wets, key=lambda f: f['d'])['g'], line, 210))

    ground_biome = 'parkland'
    if cliffs and _closest(cliffs) < 130 and len(shore) >= 2:
        ground_biome = 'cliff'
    elif coasts and _closest(coasts) < 220:
        # sand lying between the line and the water is a beach; without it the
        # ground is dune turf, which is what links means
        ground_biome = 'strand' if (sands and _closest(sands) < 150) else 'links'
    elif wets and _closest(wets) < 140 and len(shore) >= 2:
        ground_biome = 'marsh'
    elif drys and not [f for f in keep if f['t'] == 'w']:
        # the only "water" near this hole is a wash, and there is no wet water
        # anywhere in play. Angeles National, and every desert course like it.
        ground_biome = 'desert'

    def _off_shore(g0):
        if not shore:
            return 1e9
        return min(math.hypot(a[0] - b[0], a[1] - b[1]) for a in g0 for b in shore)

    # waste: ground you can be in that is not a bunker
    waste = [rnd_pts(_resample(f['g'], 28)) for f in drys[:2]]
    for f in sands[:3]:
        if ground_biome in ('strand', 'links') and _off_shore(f['g']) < 120:
            continue     # that IS the beach — crown draws it from `shore`
        waste.append(rnd_pts(_resample(f['g'], 28)))
    for f in chans[:2]:
        waste.append(rnd_pts(_resample(_buffer(f['g'], 11.0), 30)))
    waste = waste[:4]
    # a crossing creek plays exactly like crossing water: fold streams into
    # every water-behaviour computation below
    wlike = waters + streams
    tees = sorted([f for f in keep if f['t'] == 't'], key=lambda f: f['arc'])

    # fairway intervals: where the walk down the line is inside mapped fairway.
    fw = None
    if fwys and par > 3:
        runs = []
        a = 6.0
        cur = None
        while a < total:
            if any(pip(point_at_arc(line, a), fp) for fp in fwys):
                cur = [cur[0], a] if cur else [a, a]
            else:
                if cur:
                    runs.append(cur)
                cur = None
            a += 4.0
        if cur:
            runs.append(cur)
        merged = []
        for r in runs:
            if merged and r[0] - merged[-1][1] < 22:
                merged[-1][1] = r[1]
            else:
                merged.append(list(r))
        fw = [[int(round(s)), int(round(min(e + 4, total)))]
              for s, e in merged if (e - s) >= 24]
        if not fw:
            fw = None

    # front / mid / back off the green polygon, on the extended line
    has_green = bool(greens)
    if has_green:
        arcs = [line_dist(p, xl)[1] for p in greens[0]['g']]
        gfmb = (min(arcs), line_dist(centroid(greens[0]['g']), xl)[1], max(arcs))
    else:
        gfmb = (total - 10, total, total + 10)

    # bend
    bend = None; bdir = None
    if len(line) >= 3:
        cum = 0
        for i in range(1, len(line) - 1):
            cum += math.hypot(line[i][0] - line[i-1][0], line[i][1] - line[i-1][1])
            a1 = math.atan2(line[i][1] - line[i-1][1], line[i][0] - line[i-1][0])
            a2 = math.atan2(line[i+1][1] - line[i][1], line[i+1][0] - line[i][0])
            turn = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
            if abs(turn) > math.radians(14) and (bend is None or abs(turn) > abs(bend[1])):
                bend = (cum, turn); bdir = 'right' if turn > 0 else 'left'

    # carries: true water crossings first, then the key bunker
    carries = []
    crossers = [w for w in wlike if w.get('cross') and 35 < w['cross'][1] < total - 12]
    crossers.sort(key=lambda w: w['cross'][1])
    seen = []
    for w in crossers:
        if all(abs(w['cross'][1] - s) > 30 for s in seen):
            carries.append({'kind': 'water', 'at': int(w['cross'][1])})
            seen.append(w['cross'][1])
        if len(carries) >= 2: break
    bz = [b for b in bunkers if 120 < b['near'] < total - 28]
    if bz and len(carries) < 2:
        bb = max(bz, key=lambda b: area(b['g']))
        if all(abs(bb['far'] - s) > 25 for s in seen):
            carries.append({'kind': 'sand', 'at': int(round(bb['far']))})
    fw_start = fw[0][0] if (fw and fw[0][0] >= 100) else None
    if fw_start and len(carries) < 2 and all(abs(fw_start - c['at']) > 25 for c in carries):
        carries.append({'kind': 'fairway', 'at': fw_start})
    carries.sort(key=lambda c: c['at'])

    # conifer stands: timber that can actually catch a shot. DETECTED ONLY —
    # a hole with no mapped woodland gets no trees at all, because inventing a
    # treeline is the same sin as inventing a bunker (owner call, Aug 24 2026).
    # The old dogleg fallback ("if it bends, put three trees on the inside")
    # is gone; so is the unconditional par-3 backdrop ring.
    PROBES = (14.0, 22.0, 30.0, 38.0, 46.0, 55.0)

    def _dir(a):
        cum = 0.0
        for i in range(len(line) - 1):
            L = math.hypot(line[i+1][0]-line[i][0], line[i+1][1]-line[i][1])
            if cum + L >= a and L:
                return (line[i+1][0]-line[i][0])/L, (line[i+1][1]-line[i][1])/L
            cum += L
        return 0.0, -1.0

    def _timber(q):
        """Is there MAPPED timber at q? Polygon, tree row, or a tree cluster.

        GEN 6, Aug 24 2026. GEN 5 read only natural=wood / landuse=forest
        polygons, and the honest rule starved: at Bethpage Black — a course
        walled in by oak — four holes had no wood polygon within 160 yards of
        either side of the line, and across the whole catalog only 44 of 230
        GEN-5 courses got a single tree. The timber was never absent, it was
        mapped as rows and as individual trees. All three shapes are SURVEYED,
        so reading them keeps the standing rule intact: still nothing invented.

        A lone tree does not make a stand — it draws as a specimen tree if it
        is in the way. Two within 16 yards of the same spot is a treeline.
        """
        if any(pip(q, wp) for wp in wds):
            return True
        for tr in trows:
            if len(tr) >= 2 and min(seg_dist(q, tr[i], tr[i+1])[0]
                                    for i in range(len(tr) - 1)) <= 12.0:
                return True
        if len(tpts) >= 2:
            n = 0
            for tp in tpts:
                if math.hypot(q[0] - tp[0], q[1] - tp[1]) <= 16.0:
                    n += 1
                    if n >= 2:
                        return True
        return False

    def _wood_gap(a, side):
        """Distance at which timber first appears off `side`, or None."""
        p = point_at_arc(line, a)
        dx, dy = _dir(a)
        for d in PROBES:
            q = (p[0] - dy*side*d, p[1] + dx*side*d)
            if _timber(q):
                return d
        return None

    stands = []
    for side in (-1, 1):
        runs, run = [], None
        a = 40.0
        while a < total - 12:
            gap = _wood_gap(a, side)
            if gap is not None and gap <= _miss_cone(a, total):
                run = [run[0], a] if run else [a, a]
            else:
                if run and run[1] - run[0] >= 30:
                    runs.append(run)
                run = None
            a += 10.0
        if run and run[1] - run[0] >= 30:
            runs.append(run)
        # capped per side, not per hole: a tree-lined hole is lined on both
        for r in sorted(runs, key=lambda r: -(r[1] - r[0]))[:2]:
            stands.append({'side': side, 'a0': round(r[0]), 'a1': round(r[1]),
                           'count': max(2, min(6, int((r[1] - r[0]) / 45)))})

    # backdrop ring behind a green, only where timber is really behind it
    if has_green and not stands:
        gc = centroid(greens[0]['g'])
        dxb, dyb = _dir(max(0.0, total - 5))
        if any(_timber((gc[0] + dxb*d, gc[1] + dyb*d))
               for d in (18.0, 30.0, 42.0)):
            stands = [{'side': 0, 'a0': -1, 'a1': -1, 'count': 4}]

    tier = 'A' if (has_green and (bunkers or waters)) else ('B' if has_green else 'C')
    ref = int(hole['r']) if str(hole.get('r', '')).isdigit() else 0

    # ---- facts for the voice ----
    def _sd(feat_pts, at):
        p = point_at_arc(line, min(max(at, 20), total - 1))
        return 'left' if centroid(feat_pts)[0] < p[0] else 'right'
    cross_f = [w for w in wlike if w.get('cross') and 35 < w['cross'][1] < total - 12]
    cross_f.sort(key=lambda w: w['cross'][1])
    cross_exits = []
    for w in cross_f:
        if all(abs(w['cross'][1] - e) > 30 for e in cross_exits):
            cross_exits.append(int(w['cross'][1]))
    lat_f = [w for w in wlike if w not in cross_f and w['near'] < total - 40]
    gsw_f = [w for w in wlike if w not in cross_f and w['near'] > total - 60]
    bz_f = [b for b in bunkers if 150 < b['near'] < min(340, total - 60)]
    keyb = max(bz_f, key=lambda b: area(b['g'])) if bz_f else None
    lay_f = [b for b in bunkers if 340 < b['near'] < total - 60] if par == 5 else []
    layb = max(lay_f, key=lambda b: area(b['g'])) if lay_f else None
    gsb = [b for b in bunkers if b['near'] > total - 40 and b['d'] < 40]
    gsb_best = max(gsb, key=lambda b: area(b['g'])) if gsb else None
    facts = {
        'par': par, 'total': int(round(total)), 'has_green': has_green,
        'depth': int(round(gfmb[2] - gfmb[0])) if has_green else 0,
        'bend': ({'at': int(round(bend[0])), 'dir': bdir,
                  'severe': abs(bend[1]) > math.radians(30)} if bend else None),
        'cross': [e for e in cross_exits if e >= 90][:2] or None,
        'lateral': _sd(lat_f[0]['g'], lat_f[0]['near']) if lat_f else None,
        'gside_water': _sd(gsw_f[0]['g'], gsw_f[0]['near']) if gsw_f else None,
        'key_bunker': ({'side': _sd(keyb['g'], keyb['near']),
                        'near': int(round(keyb['near']))} if keyb else None),
        'corner_sand': ({'side': _sd(keyb['g'], keyb['near']),
                         'far': int(round(keyb['far']))}
                        if (keyb and bend and abs(keyb['near'] - bend[0]) < 45
                            and keyb['far'] > bend[0] + 5) else None),
        'layup_sand': ({'side': _sd(layb['g'], layb['near']),
                        'near': int(round(layb['near'])), 'far': int(round(layb['far']))}
                       if layb else None),
        'gside_sand': _sd(gsb_best['g'], gsb_best['near']) if gsb_best else None,
        'sand_count': len(bunkers),
        'stands': bool(stands),
        'water_is_river': any((w['far'] - w['near']) > 150 for w in wlike),
        'fw_start': fw_start,
        'naip_sand': naip_sand,
        'rock_count': len(rocks),
        'biome': ground_biome,
        'elev_ft': (ep[-1] if (ep := _elev_prof(elev, line_ll, line, total))
                    else _elev_ft(elev, line_ll)),
    }

    return {
        'hole': ref, 'par': par, 'tier': tier,
        'yards': {'front': int(round(gfmb[0])), 'mid': int(round(gfmb[1])),
                  'back': int(round(gfmb[2])), 'total': int(round(total))},
        'has_green': has_green,
        'line': rnd_pts(line),
        'green': rnd_pts(greens[0]['g']) if has_green else None,
        'bunkers': [rnd_pts(b['g']) for b in bunkers],
        'naip_sand': naip_sand,
        'waters': [rnd_pts(w['g']) for w in waters],
        'streams': [rnd_pts(s['g']) for s in streams[:4]],
        'rocks': [rnd_pts(r['g']) for r in rocks[:6]],
        'trees_pt': [[round(f['c'][0], 1), round(f['c'][1], 1)] for f in trees_pt[:10]],
        'hedges': [rnd_pts(f['g']) for f in hedges[:4]],
        'fences': [rnd_pts(f['g']) for f in fences[:5]],
        'bldgs': [rnd_pts(f['g']) for f in bldgs[:4]],
        'ep': ep,
        'tees': [[round(t['c'][0], 1), round(t['c'][1], 1)] for t in tees[:4]],
        'fw': fw,
        'carries': carries,
        'bend': ({'at': int(round(bend[0])), 'dir': bdir} if bend else None),
        'stands': stands,
        'biome': ground_biome,
        'shore': rnd_pts(shore) if (ground_biome != 'parkland' and shore) else [],
        'mhw': (rnd_pts(_resample(min(coasts, key=lambda f: f['d'])['g']))
                if (ground_biome == 'marsh' and coasts) else []),
        'waste': waste,
        'dunes': [],      # 3DEP ridges — filled by the elevation stage
        'turf': [],       # NAIP turf mask — filled by the imagery stage
        'facts': facts,
        'read': '', 'sign': '',
        '_srcs': ({id(greens[0]['src'])} if has_green else set())
                 | {id(t['src']) for t in tees[:4]},
    }


def _ydist(a, b):
    """Yards between two [lat, lon] points (equirectangular)."""
    k = math.cos(math.radians(a[0])) * YD_LAT
    return math.hypot((a[1] - b[1]) * k, (a[0] - b[0]) * YD_LAT)


def _cll(poly):
    """Centroid of a [lat, lon] polygon."""
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


def _synthesize(packs, holes, feats, woods, green_scorer=None):
    """The green synthesizer — stops partial courses two ways, honestly.

    A) CLAIM: a hole line exists but no green passed the filter. If an unused
       green polygon sits within 60 yd of the line's end, attach it. The green
       is real survey; only its assignment is inferred ("claimed": true).
    B) SYNTHESIZE: the hole is missing entirely. Pair a leftover green with a
       leftover tee near the mapped course, draw a straight line between two
       surveyed features, and ship it as tier "S" with "synthetic": true —
       real numbers, assumed shape, flagged everywhere.

    Nothing is ever invented except the straight line, and it says so."""
    used = set()
    for p in packs:
        used |= p.pop('_srcs', set())
    greens_all = [g for t, g in feats if t == 'g']
    tees_all = [g for t, g in feats if t == 't']
    bykey = {int(h['r']): h for h in holes if str(h.get('r', '')).isdigit()}
    # ---- A) claim orphan greens for green-less holes ----
    for i, p in enumerate(packs):
        if p['has_green']:
            continue
        h = bykey.get(p['hole'])
        if not h:
            continue
        end = h['l'][-1]
        cands = [g for g in greens_all
                 if id(g) not in used and _ydist(end, _cll(g)) < 60]
        if not cands:
            continue
        g = min(cands, key=lambda g: _ydist(end, _cll(g)))
        p2 = build_hole(h, feats, woods, claim_green=g)
        if p2 and p2['has_green']:
            used |= p2.pop('_srcs', set())
            p2['claimed'] = True
            packs[i] = p2
    # ---- B) build provisional holes from leftover green+tee pairs ----
    have = {p['hole'] for p in packs}
    if not packs:
        return packs
    expected = 18 if max(have) > 9 else 9
    missing = [r for r in range(1, expected + 1) if r not in have]
    if not missing:
        return packs
    # leftovers only count if they sit near the course we actually mapped —
    # at multi-course sites the box is full of the neighbours' features
    anchor = [q for r in sorted(have) if r in bykey for q in bykey[r]['l']][::3]
    def near_course(c):
        return any(_ydist(c, q) < 300 for q in anchor)
    og = [g for g in greens_all if id(g) not in used and near_course(_cll(g))]
    ot = [t for t in tees_all if id(t) not in used and near_course(_cll(t))]
    scored = []
    for g in og:
        gc = _cll(g)
        for t in ot:
            tc = _cll(t)
            L = _ydist(gc, tc)
            if not 90 < L < 620:
                continue
            for r in missing:
                hp, hn = bykey.get(r - 1), bykey.get(r + 1)
                # both neighbours must exist: without anchors on BOTH ends the
                # green choice is ambiguous and a neighbouring course's hole
                # can wear this slot's number (ablation-tested at Bethpage)
                if not (hp and hn):
                    continue
                d1 = _ydist(tc, hp['l'][-1])
                d2 = _ydist(gc, hn['l'][0])
                # walks between holes are short: a long leg means the pair
                # belongs to a neighbouring course, not this slot
                if d1 > 150 or d2 > 150:
                    continue
                # triangle consistency: walking prev-green -> tee -> green ->
                # next-tee must be able to span the direct gap. A short hole
                # with short walks cannot bridge a 471-yd gap — that is how a
                # neighbour's par 3 tried to wear Black's 11 (ablation-tested)
                gap = _ydist(hp['l'][-1], hn['l'][0])
                if L < gap - d1 - d2 - 30:
                    continue
                scored.append((d1 + d2, r, t, g, tc, gc))
    # confidence gate: a slot is only filled when ONE pairing clearly wins.
    # At dense multi-course sites many wrong pairs pass the geometry gates
    # (ablation at Bethpage: 5/10 impostors without this) — a slot with a
    # close runner-up that disagrees on length is ambiguous, so decline it.
    byslot = {}
    for cand in scored:
        byslot.setdefault(cand[1], []).append(cand)
    scored = []
    for r, cands in byslot.items():
        # a hole owns several tee boxes: same-green candidates are one hole,
        # not rivals — keep the back tee (the longest of the cluster)
        bygreen = {}
        for c in cands:
            k = id(c[3])
            L = _ydist(_cll(c[3]), _cll(c[2]))
            if k not in bygreen or L > bygreen[k][0]:
                bygreen[k] = (L, c)
        picks = sorted(bygreen.values(), key=lambda x: x[1][0])
        bestL, best = picks[0]
        rivals = [p for p in picks[1:]
                  if p[1][0] < best[0] + 60 and abs(p[0] - bestL) > 40]
        # imagery tie-break: a real green sits on smooth healthy turf; if the
        # best candidate looks like a green from the air and every rival does
        # not, the ambiguity is resolved rather than declined (NAIP votes,
        # it never overrides an unambiguous geometric answer)
        if rivals and green_scorer is not None:
            try:
                if (green_scorer(_cll(best[3])) >= 0.99 and
                        all(green_scorer(_cll(p[1][3])) < 0.6 for p in rivals)):
                    rivals = []
            except Exception:
                pass
        if best[0] < 240 and not rivals:
            scored.append(best)
    scored.sort(key=lambda x: x[0])
    taken_r, taken_f = set(), set()
    for s, r, t, g, tc, gc in scored:
        if r in taken_r or id(g) in taken_f or id(t) in taken_f:
            continue
        p = build_hole({'r': str(r), 'p': '', 'l': [list(tc), list(gc)]},
                       feats, woods)
        if not p or not p['has_green']:
            continue
        p.pop('_srcs', None)
        p['tier'] = 'S'
        p['synthetic'] = True
        p['facts']['synthetic'] = True
        packs.append(p)
        taken_r.add(r); taken_f.add(id(g)); taken_f.add(id(t))
    packs.sort(key=lambda p: p['hole'])
    return packs


def _match_course_holes(holes, course_name):
    """A dense site (Bethpage: five courses, 90 holes in one box) needs the
    hole NAMES matched to the course name. Group holes by their name prefix
    ("Black 4" -> "black"); pick the group whose prefix appears in the course
    name, else the largest group. Duplicate refs keep the first seen."""
    groups = {}
    for h in holes:
        prefix = re.sub(r'\s*\d+$', '', (h.get('n') or '').strip()).strip().lower()
        groups.setdefault(prefix, []).append(h)
    if len(groups) > 1:
        cn = (course_name or '').lower()
        def score(p):
            toks = [t for t in re.split(r'[^a-z]+', p) if len(t) > 2]
            return sum(1 for t in toks if t in cn)
        best = max(groups, key=lambda p: (score(p), len(groups[p])))
        if score(best) == 0:
            best = max(groups, key=lambda p: len(groups[p]))
        holes = groups[best]
    seen = set(); out = []
    for h in holes:
        if h['r'] in seen:
            continue
        seen.add(h['r']); out.append(h)
    return out


def build_course(data, green_scorer=None, elev=None):
    """data = the pack format from osm.py. Returns (packs, coverage).
    green_scorer: optional NAIP turf-vote fn([lat,lon])->0..1 (see naip.py).
    elev: optional DEM sampler fn([lat,lon])->meters (see naip.py)."""
    holes = [h for h in data['h'] if str(h.get('r', '')).isdigit()]
    holes = _match_course_holes(holes, data['c'].get('n', ''))
    holes.sort(key=lambda h: int(h['r']))
    woods = [g for t, g in data['f'] if t == 'x']
    feats = [(t, g) for t, g in data['f'] if t != 'x']
    packs = []
    for h in holes:
        p = build_hole(h, feats, woods, seed=int(h['r']), elev=elev)
        if p: packs.append(p)
    packs = _synthesize(packs, holes, feats, woods, green_scorer=green_scorer)
    # ---- course-aware voice pass: ranks, then compose with no repeats ----
    if packs:
        last = max(p['hole'] for p in packs)
        first = min(p['hole'] for p in packs)
        longest = max(packs, key=lambda p: p['yards']['mid'])
        shortest = min(packs, key=lambda p: p['yards']['mid'])
        rng, used_reads, used_signs = voice.make_course_voice(data['c']['k'])
        for p in packs:
            f = p['facts']
            f['rank'] = ('longest' if p is longest else
                         ('shortest' if p is shortest else None))
            p['read'] = voice.compose_read(f, rng, used_reads)
            p['sign'] = voice.pick_sign(f, rng, used_signs,
                                        is_last=(p['hole'] == last),
                                        is_first=(p['hole'] == first))
            if p.get('synthetic'):
                p['read'] = ('Provisional hole — the green is surveyed; the '
                             'line to it is assumed straight. Trust the '
                             'numbers, scout the shape.')
    for p in packs:
        p.pop('_srcs', None)
    tiers = {}
    for p in packs:
        tiers[p['tier']] = tiers.get(p['tier'], 0) + 1
    real = [p for p in packs if p['tier'] != 'S']
    coverage = {
        'course_key': data['c']['k'],
        'holes': len(packs),
        'tiers': tiers,
        'par': sum(p['par'] for p in packs),
        'yds': sum(p['yards']['mid'] for p in packs),
        'status': ('full' if len(real) >= 17 else ('partial' if real else 'none')),
    }
    return packs, coverage


if __name__ == '__main__':
    import sys
    data = json.load(open(sys.argv[1]))
    packs, cov = build_course(data)
    print(json.dumps(cov))
    if len(sys.argv) > 2:
        json.dump(packs, open(sys.argv[2], 'w'))
        print('wrote', sys.argv[2])
