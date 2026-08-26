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
import json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import naip                                       # noqa: E402

CELL = 11          # analysis cell, px (~11 m at this chip's 1 m/px)


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


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: canopy.py <course_key>')
    key = sys.argv[1].strip()
    q = urllib.parse.quote(key, safe='')
    course = (_get(f'courses?select=key,name,info&key=eq.{q}') or [{}])[0]
    if not course:
        sys.exit(f'no course {key}')
    info = course.get('info') or {}
    lat, lng = info.get('lat'), info.get('lng')
    if lat is None or lng is None:
        sys.exit('course has no coordinates')

    nir, red, bbox = naip._fetch(lat, lng)
    H, W = nir.shape
    c = classify(nir, red)
    gh, gw = c['shape']
    n = gh * gw

    print(f'chip {W}x{H}  cells {gw}x{gh} @ {c["cell"]}px', flush=True)
    print(f'vegetated   {int(c["veg"].sum()):>7} / {n}  ({c["veg"].mean()*100:5.1f}%)', flush=True)
    print(f'canopy      {int(c["canopy"].sum()):>7} / {n}  ({c["canopy"].mean()*100:5.1f}%)', flush=True)
    print(f'turf        {int(c["turf"].sum()):>7} / {n}  ({c["turf"].mean()*100:5.1f}%)', flush=True)
    print(f'short turf  {int(c["short"].sum()):>7} / {n}  ({c["short"].mean()*100:5.1f}%)', flush=True)
    print(f'otsu separation {c["otsu_sep"]:.3f}   '
          f'(below ~0.35 the vegetated population is one lump, '
          f'and the split is not real)', flush=True)

    # ---- the picture ----
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
    layers = {'canopy': rects(c['canopy'], 'ca'),
              'turf': rects(c['turf'], 'tu'),
              'short': rects(c['short'], 'sh')}
    panels = ''.join(
        f'<figure><figcaption>{k}</figcaption>'
        f'<div class="stage"><img src="{img}" alt="">'
        f'<svg viewBox="0 0 1000 1000">{v}</svg></div></figure>'
        for k, v in [('aerial', ''), ('canopy', layers['canopy']),
                     ('turf', layers['turf']), ('short turf', layers['short'])])

    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Canopy prototype &mdash; {course.get('name') or key}</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Archivo:wght@400;600&display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#F2F1EC;color:#0C1710;font-family:Archivo,system-ui,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:40px 20px 80px}}
h1{{font-family:Fraunces,Georgia,serif;font-size:34px;margin:0 0 6px;letter-spacing:-.015em}}
p.dek{{color:#6D7770;max-width:74ch;margin:0 0 22px;font-size:15px}}
table{{border-collapse:collapse;font-size:13.5px;background:#fff;border:1px solid #E3E3DC;margin:0 0 26px}}
th,td{{padding:7px 14px;border-bottom:1px solid #EEEEE8;text-align:left}}
th{{font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:#6D7770}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}}
figure{{margin:0}}
figcaption{{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:#6D7770;
 margin:0 0 6px;font-weight:600}}
.stage{{position:relative;aspect-ratio:1;border:1px solid #E3E3DC;border-radius:3px;overflow:hidden}}
.stage img,.stage svg{{position:absolute;inset:0;width:100%;height:100%}}
.ca{{fill:#14432A;fill-opacity:.55}}
.tu{{fill:#C7F24A;fill-opacity:.40}}
.sh{{fill:#FFFFFF;fill-opacity:.55}}
@media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Canopy prototype &mdash; {course.get('name') or key}</h1>
<p class="dek">Timber and mown ground taken off the NAIP chip by texture rather than
by colour: both a fairway and an oak stand are vegetated, but a fairway is smooth and
a canopy is rough, and that survives the per-chip contrast stretch that makes absolute
NDVI useless. The split is Otsu on this chip's own vegetated cells. Separation below
about 0.35 means there was only one population and the answer should not be believed.</p>
<table><tbody>
<tr><th>Vegetated</th><td class="n">{c['veg'].mean()*100:.1f}%</td></tr>
<tr><th>Canopy</th><td class="n">{c['canopy'].mean()*100:.1f}%</td></tr>
<tr><th>Turf</th><td class="n">{c['turf'].mean()*100:.1f}%</td></tr>
<tr><th>Short turf</th><td class="n">{c['short'].mean()*100:.1f}%</td></tr>
<tr><th>Otsu separation</th><td class="n">{c['otsu_sep']:.3f}</td></tr>
</tbody></table>
<div class="grid">{panels}</div>
</div></body></html>'''
    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    open(os.path.join(ROOT, 'demo', f'canopy_{key}.html'), 'w').write(html)
    print(f'wrote demo/canopy_{key}.html', flush=True)


if __name__ == '__main__':
    main()
