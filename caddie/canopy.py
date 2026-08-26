#!/usr/bin/env python3
"""PROTOTYPE: timber and fairway off the NAIP chip, not off OpenStreetMap.

Measured on two tree-lined parkland courses (caddie-truth, Aug 26 2026):
Bobby Jones in Atlanta has its nearest mapped wood a median 567 yards from
the playing line, and Idyl Wyld in Detroit has no mapped timber at all. The
probe ladder in generate.py is not too short -- the trees are simply not in
OSM. The only measured source left is the imagery we already fetch.

The split this leans on is texture, not colour. Both a fairway and an oak
stand are vegetated, and exportImage stretches every chip differently so
absolute NDVI proves nothing (see naip.py). But mown turf is SMOOTH and a
canopy is ROUGH, and that survives any per-chip stretch:

    canopy  = vegetated AND high local NDVI variance
    turf    = vegetated AND low  local NDVI variance
    fairway = the smoothest turf, in a band that runs with the hole

The threshold between them is found with Otsu on this chip's own vegetated
population, and the run reports how separable that population actually was --
a unimodal chip means the split is arbitrary and should not be trusted.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python caddie/canopy.py KEY

Writes demo/canopy_<course_key>.html: the aerial with what it found drawn on
top, so the classification can be looked at rather than believed.
"""
import json, math, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import naip                                       # noqa: E402

CELL = 11          # analysis cell, px (~11 m at this chip's 1 m/px)



PAGE_CSS = """
body{margin:0;background:#F2F1EC;color:#0C1710;font-family:Archivo,system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 20px 80px}
h1{font-family:Fraunces,Georgia,serif;font-size:34px;margin:0 0 6px;letter-spacing:-.015em}
p.dek{color:#6D7770;max-width:74ch;margin:0 0 22px;font-size:15px}
table{border-collapse:collapse;font-size:13.5px;background:#fff;border:1px solid #E3E3DC;margin:0 0 26px}
th,td{padding:7px 14px;border-bottom:1px solid #EEEEE8;text-align:left}
th{font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:#6D7770}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}
figure{margin:0}
figcaption{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:#6D7770;
 margin:0 0 6px;font-weight:600}
.stage{position:relative;aspect-ratio:1;border:1px solid #E3E3DC;border-radius:3px;overflow:hidden}
.stage img,.stage svg{position:absolute;inset:0;width:100%;height:100%}
.ca{fill:#14432A;fill-opacity:.55}
.tu{fill:#C7F24A;fill-opacity:.40}
.sh{fill:#FFFFFF;fill-opacity:.55}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
"""

INDEX_CSS = """
body{margin:0;background:#F2F1EC;color:#0C1710;font-family:Archivo,system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:44px 20px 90px}
h1{font-family:Fraunces,Georgia,serif;font-size:36px;margin:0 0 8px;letter-spacing:-.015em}
p.dek{color:#6D7770;max-width:80ch;margin:0 0 26px;font-size:15px;line-height:1.6}
p.dek b{color:#0C1710}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:#fff;
 border:1px solid #E3E3DC;border-radius:3px}
th,td{padding:9px 12px;border-bottom:1px solid #EEEEE8;text-align:left;vertical-align:middle}
thead th{font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:#6D7770;
 background:#F7F6F1;position:sticky;top:0}
td.n{text-align:right;font-variant-numeric:tabular-nums}
td.th{width:112px;padding:5px 8px}
td.th img{display:block;width:104px;height:76px;object-fit:cover;border-radius:2px;
 border:1px solid #E3E3DC}
td.v{font-size:12px}
span.k{color:#9AA394;font-size:11px;font-family:ui-monospace,Menlo,monospace}
a{color:#14432A}
tr.ok td.v{color:#2F6B45}
tr.bad{background:#FDF6F2}
tr.bad td.v{color:#A8552A;font-weight:600}
"""

def _get(path):
    url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + path
    key = os.environ['SUPABASE_SERVICE_KEY']
    req = urllib.request.Request(url, headers={
        'apikey': key, 'Authorization': 'Bearer ' + key,
        'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _otsu(v, bins=128):
    """Threshold that best splits v into two populations, plus how good the
    split is (between-class variance over total variance, 0..1)."""
    import numpy as np
    v = v[np.isfinite(v)]
    if v.size < 32:
        return None, 0.0
    lo, hi = float(v.min()), float(v.max())
    if hi - lo < 1e-9:
        return None, 0.0
    hist, edges = np.histogram(v, bins=bins, range=(lo, hi))
    p = hist.astype(np.float64) / hist.sum()
    mids = (edges[:-1] + edges[1:]) / 2.0
    w0 = np.cumsum(p)
    w1 = 1.0 - w0
    m0 = np.cumsum(p * mids) / np.maximum(w0, 1e-12)
    mt = float((p * mids).sum())
    m1 = (mt - np.cumsum(p * mids)) / np.maximum(w1, 1e-12)
    sb = w0 * w1 * (m0 - m1) ** 2
    k = int(np.nanargmax(sb))
    total = float(v.var())
    return float(mids[k]), float(sb[k] / total) if total > 0 else 0.0


def classify(nir, red, cell=CELL):
    """-> dict of boolean cell grids and the numbers behind them."""
    import numpy as np
    nd = (nir - red) / (nir + red + 1e-6)
    H, W = nd.shape
    hh, ww = (H // cell) * cell, (W // cell) * cell
    blk = nd[:hh, :ww].reshape(hh // cell, cell, ww // cell, cell)
    mu = blk.mean(axis=(1, 3))
    sd = blk.std(axis=(1, 3))

    # IS THIS VEGETATION AT ALL. Only a floor -- it must not cut into the
    # vegetated mass, because on a parkland course vegetation IS most of the
    # chip and any median- or Otsu-anchored threshold splits the turf in half
    # (measured on synthetic scenes: a median anchor classified 0% of a
    # fully-turfed chip as turf). Anchored to the green tail instead, with an
    # absolute backstop for chips that are nearly all bare.
    #
    # naip.py records that exportImage stretches every chip, so the same
    # fairway can read 0.24 on one course and 0.12 on the next. A scene built
    # to that worst case -- fairway 0.12, canopy 0.17 -- still comes out 94%
    # turf and 93% canopy through this floor.
    s = np.sort(mu.ravel())
    p90 = float(s[int(s.size * 0.90)])
    veg_thr = max(0.10, 0.35 * p90)
    veg = mu > veg_thr

    # texture splits the vegetated ground into mown and not
    rough_thr, sep = _otsu(sd[veg])
    if rough_thr is None:
        rough_thr, sep = float(np.median(sd)), 0.0
    canopy = veg & (sd >= rough_thr)
    turf = veg & (sd < rough_thr)

    # the smoothest quarter of the turf is the mown-shortest: fairway and
    # green. Reported separately because it is the weaker claim of the two --
    # rough is mown too, just longer.
    if turf.any():
        short_thr = float(np.quantile(sd[turf], 0.35))
    else:
        short_thr = 0.0
    short = turf & (sd <= short_thr)

    return {'mu': mu, 'sd': sd, 'veg': veg, 'canopy': canopy, 'turf': turf,
            'short': short, 'veg_thr': veg_thr, 'rough_thr': rough_thr,
            'otsu_sep': sep, 'short_thr': short_thr, 'cell': cell,
            'shape': (hh // cell, ww // cell)}


def cells_to_ll(grid, bbox, H, W, cell):
    """Boolean cell grid -> [[lat, lon], ...] of cell centres."""
    import numpy as np
    ys, xs = np.nonzero(grid)
    out = []
    for y, x in zip(ys.tolist(), xs.tolist()):
        lat = bbox[3] - (y * cell + cell / 2) / H * (bbox[3] - bbox[1])
        lon = bbox[0] + (x * cell + cell / 2) / W * (bbox[2] - bbox[0])
        out.append([round(lat, 6), round(lon, 6)])
    return out



def corridor_stats(c, bbox, H, W, holes, near_yd=25.0, flank_lo=40.0, flank_hi=90.0):
    """The number that decides whether this is safe to ship.

    Trees belong OFF the playing line. So measure two bands and compare them:
    how much of the corridor itself the classifier calls canopy (should be
    small -- a fairway is not a wood), and how much of the flanking band it
    calls canopy (should be substantial on a parkland course, because that is
    where the treeline stands). A classifier merely painting green ground
    green scores the same in both bands and is worth nothing.
    """
    import numpy as np
    cell = c['cell']
    gh, gw = c['shape']
    mpx_x = (bbox[2] - bbox[0]) * 111320.0 * math.cos(
        math.radians((bbox[1] + bbox[3]) / 2)) / W
    mpx_y = (bbox[3] - bbox[1]) * 110540.0 / H
    yd_x = mpx_x * cell * 1.0936
    yd_y = mpx_y * cell * 1.0936

    gy, gx = np.mgrid[0:gh, 0:gw]
    cy = ((gy + 0.5) * yd_y).astype(np.float32)
    cx = ((gx + 0.5) * yd_x).astype(np.float32)

    def to_cellyd(ll):
        px = (ll[1] - bbox[0]) / (bbox[2] - bbox[0]) * W / cell
        py = (bbox[3] - ll[0]) / (bbox[3] - bbox[1]) * H / cell
        return px * yd_x, py * yd_y

    best = np.full((gh, gw), 1e9, dtype=np.float32)
    segs = 0
    for h in holes:
        ll = h.get('l') or []
        if len(ll) < 2:
            continue
        pts = [to_cellyd(q) for q in ll]
        for i in range(len(pts) - 1):
            ax, ay = pts[i]; bx, by = pts[i + 1]
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            if L < 1e-9:
                continue
            t = np.clip(((cx - ax) * dx + (cy - ay) * dy) / L, 0.0, 1.0)
            d = np.hypot(cx - (ax + t * dx), cy - (ay + t * dy))
            np.minimum(best, d, out=best)
            segs += 1
    if not segs:
        return None

    on = best <= near_yd
    fl = (best > flank_lo) & (best <= flank_hi)

    def pct(mask, sel):
        n = int(sel.sum())
        return None if n == 0 else round(100.0 * float((mask & sel).sum()) / n, 1)

    return {'segs': segs,
            'on_cells': int(on.sum()), 'flank_cells': int(fl.sum()),
            'canopy_on': pct(c['canopy'], on),
            'canopy_flank': pct(c['canopy'], fl),
            'turf_on': pct(c['turf'], on),
            'turf_flank': pct(c['turf'], fl)}



# ---- parameter sweep -------------------------------------------------------
# Three suspects for why the first run found no contrast between the corridor
# and its flank (1 of 10 courses passed, median gap 2.0 points):
#   1. an 11 m cell straddles the fairway edge, so edge cells contain both
#      mown turf and treeline, read rough, and smear canopy onto the corridor
#   2. boundary cells belong to neither class and should be dropped
#   3. a 25-yard "on the line" band is already in the treeline on a tight
#      hole, which makes the test unfair to itself
# All three are measured together here, off one chip fetch per course.

CONFIGS = [(6, 0), (6, 1), (11, 0), (11, 1)]     # (cell px, erode passes)
BANDS = [12.0, 25.0]                             # "on the line" half-width, yd


def erode(mask, passes=1):
    """Drop cells that touch a non-canopy neighbour: a boundary cell contains
    both classes and belongs to neither."""
    import numpy as np
    m = mask
    for _ in range(passes):
        k = np.ones_like(m)
        k[1:, :] &= m[:-1, :]
        k[:-1, :] &= m[1:, :]
        k[:, 1:] &= m[:, :-1]
        k[:, :-1] &= m[:, 1:]
        m = m & k
    return m


def dist_grid(c, bbox, H, W, holes):
    """Yards from each cell centre to the nearest playing line."""
    import numpy as np
    cell = c['cell']
    gh, gw = c['shape']
    mpx_x = (bbox[2] - bbox[0]) * 111320.0 * math.cos(
        math.radians((bbox[1] + bbox[3]) / 2)) / W
    mpx_y = (bbox[3] - bbox[1]) * 110540.0 / H
    yd_x = mpx_x * cell * 1.0936
    yd_y = mpx_y * cell * 1.0936
    gy, gx = np.mgrid[0:gh, 0:gw]
    cy = ((gy + 0.5) * yd_y).astype(np.float32)
    cx = ((gx + 0.5) * yd_x).astype(np.float32)

    def to_cellyd(ll):
        px = (ll[1] - bbox[0]) / (bbox[2] - bbox[0]) * W / cell
        py = (bbox[3] - ll[0]) / (bbox[3] - bbox[1]) * H / cell
        return px * yd_x, py * yd_y

    best = np.full((gh, gw), 1e9, dtype=np.float32)
    segs = 0
    for h in holes:
        ll = h.get('l') or []
        if len(ll) < 2:
            continue
        pts = [to_cellyd(q) for q in ll]
        for i in range(len(pts) - 1):
            ax, ay = pts[i]; bx, by = pts[i + 1]
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            if L < 1e-9:
                continue
            t = np.clip(((cx - ax) * dx + (cy - ay) * dy) / L, 0.0, 1.0)
            np.minimum(best, np.hypot(cx - (ax + t * dx), cy - (ay + t * dy)), out=best)
            segs += 1
    return (best, segs) if segs else (None, 0)


def param_matrix(nir, red, bbox, H, W, holes):
    """Every (cell, erode, band) combination, off one chip."""
    out = []
    for cell, er in CONFIGS:
        c = classify(nir, red, cell=cell)
        can = erode(c['canopy'], er) if er else c['canopy']
        best, segs = dist_grid(c, bbox, H, W, holes)
        if best is None:
            continue
        for band in BANDS:
            on = best <= band
            fl = (best > 40.0) & (best <= 90.0)
            def pct(m, sel):
                n = int(sel.sum())
                return None if n == 0 else round(100.0 * float((m & sel).sum()) / n, 1)
            o, f = pct(can, on), pct(can, fl)
            out.append({'cell': cell, 'erode': er, 'band': band,
                        'sep': round(c['otsu_sep'], 3),
                        'canopy': round(float(can.mean()) * 100, 1),
                        'on': o, 'flank': f,
                        'gap': None if (o is None or f is None) else round(f - o, 1)})
    return out


def one(key):
    """Run the classifier over one course. Returns a row for the index."""
    q = urllib.parse.quote(key, safe='')
    course = (_get(f'courses?select=key,name,info,market_key&key=eq.{q}') or [{}])[0]
    if not course:
        return {'key': key, 'error': 'no such course'}
    info = course.get('info') or {}
    lat, lng = info.get('lat'), info.get('lng')
    if lat is None or lng is None:
        return {'key': key, 'error': 'no coordinates'}

    nir, red, bbox = naip._fetch(lat, lng)
    H, W = nir.shape
    c = classify(nir, red)

    st, feats, mx = None, None, []
    try:
        import osm
        feats = osm.fetch_course(key, course.get('name') or '',
                                 course.get('market_key') or '', lat, lng)
        holes = (feats or {}).get('h') or []
        if holes:
            st = corridor_stats(c, bbox, H, W, holes)
            mx = param_matrix(nir, red, bbox, H, W, holes)
    except Exception as e:                      # OSM is a nice-to-have here
        print(f'  [{key}] corridor stats unavailable: {e}', flush=True)

    row = {'key': key, 'name': course.get('name') or key,
           'lat': lat, 'lng': lng,
           'sep': round(c['otsu_sep'], 3),
           'canopy': round(float(c['canopy'].mean()) * 100, 1),
           'turf': round(float(c['turf'].mean()) * 100, 1),
           'short': round(float(c['short'].mean()) * 100, 1),
           'holes': len((feats or {}).get('h') or [])}
    row['matrix'] = mx
    row.update(st or {})
    row['verdict'] = verdict(row)
    write_page(key, course, bbox, H, W, c, st)
    print(f'  {key:<44} sep {row["sep"]:.2f}  canopy {row["canopy"]:>5.1f}%  '
          f'on-line {str(row.get("canopy_on")):>5}  flank {str(row.get("canopy_flank")):>5}  '
          f'{row["verdict"]}', flush=True)
    return row


def verdict(r):
    """Plain words, so a bad course cannot hide behind a number."""
    if r.get('sep', 0) < 0.35:
        return 'UNRELIABLE - one population'
    on, fl = r.get('canopy_on'), r.get('canopy_flank')
    if on is None or fl is None:
        return 'no holes to check against'
    if on > 25:
        return 'BLEEDING onto the corridor'
    if fl - on < 10:
        return 'NO CONTRAST - not finding treelines'
    return 'ok'


def write_page(key, course, bbox, H, W, c, st):
    px = lambda ll: (((ll[1] - bbox[0]) / (bbox[2] - bbox[0])) * 1000.0,
                     ((bbox[3] - ll[0]) / (bbox[3] - bbox[1])) * 1000.0)
    side = 1000.0 * c['cell'] / W

    def rects(grid, cls):
        out = []
        for ll in cells_to_ll(grid, bbox, H, W, c['cell']):
            x, y = px(ll)
            out.append(f'<rect class="{cls}" x="{x-side/2:.2f}" y="{y-side/2:.2f}" '
                       f'width="{side:.2f}" height="{side:.2f}"/>')
        return ''.join(out)

    img = (f'{naip.SERVER}?bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'
           f'&bboxSR=4326&imageSR=4326&size=1400,1400&format=jpg&f=image')
    panels = ''.join(
        f'<figure><figcaption>{k}</figcaption>'
        f'<div class="stage"><img src="{img}" alt="">'
        f'<svg viewBox="0 0 1000 1000">{v}</svg></div></figure>'
        for k, v in [('aerial', ''), ('canopy', rects(c['canopy'], 'ca')),
                     ('turf', rects(c['turf'], 'tu')),
                     ('short turf', rects(c['short'], 'sh'))])
    strows = ''
    if st:
        strows = (f'<tr><th>Canopy on the line</th><td class="n">{st["canopy_on"]}%</td></tr>'
                  f'<tr><th>Canopy in the flank</th><td class="n">{st["canopy_flank"]}%</td></tr>'
                  f'<tr><th>Turf on the line</th><td class="n">{st["turf_on"]}%</td></tr>')
    name = course.get('name') or key
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Canopy prototype &mdash; {name}</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600'
            '&family=Archivo:wght@400;600&display=swap" rel="stylesheet">'
            '<style>' + PAGE_CSS + '</style></head><body><div class="wrap">'
            f'<h1>Canopy prototype &mdash; {name}</h1>'
            '<p class="dek">Timber and mown ground taken off the NAIP chip by texture rather '
            'than colour: both a fairway and an oak stand are vegetated, but a fairway is '
            'smooth and a canopy is rough, and that survives the per-chip contrast stretch '
            'that makes absolute NDVI useless. Separation below about 0.35 means there was '
            'only one population and the answer should not be believed.</p>'
            '<table><tbody>'
            f'<tr><th>Vegetated</th><td class="n">{c["veg"].mean()*100:.1f}%</td></tr>'
            f'<tr><th>Canopy</th><td class="n">{c["canopy"].mean()*100:.1f}%</td></tr>'
            f'<tr><th>Turf</th><td class="n">{c["turf"].mean()*100:.1f}%</td></tr>'
            f'<tr><th>Short turf</th><td class="n">{c["short"].mean()*100:.1f}%</td></tr>'
            f'<tr><th>Otsu separation</th><td class="n">{c["otsu_sep"]:.3f}</td></tr>'
            + strows + '</tbody></table>'
            f'<div class="grid">{panels}</div></div></body></html>')
    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    open(os.path.join(ROOT, 'demo', f'canopy_{key}.html'), 'w').write(html)


def write_index(rows):
    def cell(v, suffix='%'):
        return '&mdash;' if v is None else f'{v}{suffix}'
    trs = []
    for r in rows:
        if r.get('error'):
            trs.append(f'<tr class="bad"><td>{r["key"]}</td><td colspan="7">{r["error"]}</td></tr>')
            continue
        cls = ('ok' if r['verdict'] == 'ok' else 'bad')
        thumb = (f'{naip.SERVER}?bbox={r["lng"]-0.011},{r["lat"]-0.008},'
                 f'{r["lng"]+0.011},{r["lat"]+0.008}'
                 f'&bboxSR=4326&imageSR=4326&size=220,160&format=jpg&f=image')
        trs.append(
            f'<tr class="{cls}"><td class="th"><img src="{thumb}" alt="" loading="lazy"></td>'
            f'<td><a href="canopy_{r["key"]}.html">{r["name"]}</a><br>'
            f'<span class="k">{r["key"]}</span></td>'
            f'<td class="n">{r["sep"]:.2f}</td><td class="n">{cell(r["canopy"])}</td>'
            f'<td class="n">{cell(r.get("canopy_on"))}</td>'
            f'<td class="n">{cell(r.get("canopy_flank"))}</td>'
            f'<td class="n">{cell(r.get("turf_on"))}</td>'
            f'<td class="v">{r["verdict"]}</td></tr>')
    okn = sum(1 for r in rows if r.get('verdict') == 'ok')
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Canopy review</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600'
            '&family=Archivo:wght@400;600&display=swap" rel="stylesheet">'
            '<style>' + INDEX_CSS + '</style></head><body><div class="wrap">'
            '<h1>Canopy review</h1>'
            f'<p class="dek"><b>{okn} of {len(rows)}</b> courses pass. The pair that matters is '
            '<b>canopy on the line</b> against <b>canopy in the flank</b>: trees belong off the '
            'playing line, so a classifier worth shipping scores low on the first and high on '
            'the second. Equal numbers mean it is only painting green ground green. Rows are '
            'red when the split was unreliable, when canopy is bleeding onto the corridor, or '
            'when there is no contrast between the bands.</p>'
            '<table><thead><tr><th></th><th>Course</th><th>Sep</th><th>Canopy</th>'
            '<th>On line</th><th>Flank</th><th>Turf on line</th><th>Verdict</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div></body></html>')
    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    open(os.path.join(ROOT, 'demo', 'canopy_index.html'), 'w').write(html)



def write_matrix(rows):
    """Which parameter combination, if any, actually separates the corridor
    from its flank. One row per (cell, erode, band); the median gap across
    courses is the number that decides it."""
    import statistics
    have = [r for r in rows if r.get('matrix')]
    if not have:
        return
    keys, agg = [], {}
    for r in have:
        for m in r['matrix']:
            k = (m['cell'], m['erode'], m['band'])
            if k not in agg:
                agg[k] = []
                keys.append(k)
            if m['gap'] is not None:
                agg[k].append((r['name'], m))
    trs = []
    for k in keys:
        items = agg[k]
        gaps = [m['gap'] for _, m in items]
        if not gaps:
            continue
        med = statistics.median(gaps)
        passes = sum(1 for _, m in items
                     if m['gap'] >= 10 and (m['on'] or 0) <= 25)
        cls = 'ok' if med >= 10 else 'bad'
        trs.append(f'<tr class="{cls}"><td class="n">{k[0]}</td><td class="n">{k[1]}</td>'
                   f'<td class="n">{k[2]:.0f}</td><td class="n">{med:.1f}</td>'
                   f'<td class="n">{min(gaps):.1f}</td><td class="n">{max(gaps):.1f}</td>'
                   f'<td class="n">{passes} / {len(gaps)}</td></tr>')
    det = []
    for r in have:
        cells = ''.join(f'<td class="n">{"" if m["gap"] is None else m["gap"]}</td>'
                        for m in r['matrix'])
        det.append(f'<tr><td>{r["name"]}</td>{cells}</tr>')
    hdr = ''.join(f'<th>{m["cell"]}px e{m["erode"]}<br>b{m["band"]:.0f}</th>'
                  for m in have[0]['matrix'])
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Canopy parameter sweep</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600'
            '&family=Archivo:wght@400;600&display=swap" rel="stylesheet">'
            '<style>' + INDEX_CSS + ' td,th{padding:7px 10px}</style>'
            '</head><body><div class="wrap"><h1>Canopy parameter sweep</h1>'
            '<p class="dek">Cell size, erosion and the width of the on-the-line band, '
            'every combination measured off the same chips. <b>Gap</b> is canopy in the '
            'flank minus canopy on the line: it is the whole test, because a classifier '
            'that is only painting green ground green scores zero here however good the '
            'overlay looks. A row passes a course when the gap clears 10 points and no '
            'more than a quarter of the corridor is called canopy. Handed a synthetic '
            'scene with a treeline planted 40&ndash;90 yards out, this harness scores '
            'a gap of 96, so a low number here is the courses talking, not the ruler.</p>'
            '<table><thead><tr><th>Cell px</th><th>Erode</th><th>Band yd</th>'
            '<th>Median gap</th><th>Min</th><th>Max</th><th>Courses passing</th></tr>'
            f'</thead><tbody>{"".join(trs)}</tbody></table>'
            '<h1 style="font-size:22px;margin-top:38px">Per course</h1>'
            f'<table><thead><tr><th>Course</th>{hdr}</tr></thead>'
            f'<tbody>{"".join(det)}</tbody></table></div></body></html>')
    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    open(os.path.join(ROOT, 'demo', 'canopy_matrix.html'), 'w').write(html)


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: canopy.py <course_key>[,<course_key>...]')
    keys = [k.strip() for k in sys.argv[1].split(',') if k.strip()]
    rows = []
    for k in keys:
        try:
            rows.append(one(k))
        except Exception as e:
            print(f'  [{k}] FAILED: {e}', flush=True)
            rows.append({'key': k, 'error': str(e)[:120]})
    if not [r for r in rows if not r.get('error')]:
        sys.exit('every course failed')
    write_index(rows)
    write_matrix(rows)
    okn = sum(1 for r in rows if r.get('verdict') == 'ok')
    print(f'wrote demo/canopy_index.html and canopy_matrix.html  ({okn} of {len(rows)} pass)', flush=True)


if __name__ == '__main__':
    main()
