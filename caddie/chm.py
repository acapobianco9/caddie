#!/usr/bin/env python3
"""Trees, from a measured canopy height model.

Texture failed because NDVI variance is a proxy for a tree. Height is not a
proxy -- a pixel that reads 14 metres is a tree, and no amount of mowing
stripes or contrast stretch changes that. WRI and Meta publish a global canopy
height model as public cloud-optimised GeoTIFFs on S3; a COG lets us pull only
the couple of thousand pixels over one golf course rather than the whole tile.

This is a survey, the same standing as OSM -- just one nobody had to
volunteer for. So reading it keeps the rule intact: still nothing invented.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python caddie/chm.py KEY[,KEY...]

Writes demo/chm_<key>.html per course and demo/chm_index.html.
"""
import json, math, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

BUCKET = 'https://dataforgood-fb-data.s3.amazonaws.com'
SOURCES = [
    ('v2', f'{BUCKET}/forests/v2/global/dinov3_global_chm_v2_ml3/chm/%s.tif'),
    ('v1', f'{BUCKET}/forests/v1/alsgedi_global_v6_float/chm/%s.tif'),
]
ZOOM = 10
TREE_M = 3.0        # a golf tree; below this is scrub, hedge or a bad pixel
PROBES = [10.0, 16.0, 22.0, 30.0, 38.0, 46.0, 55.0, 65.0, 75.0, 90.0, 110.0]


def _get(path):
    url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + path
    key = os.environ['SUPABASE_SERVICE_KEY']
    req = urllib.request.Request(url, headers={
        'apikey': key, 'Authorization': 'Bearer ' + key,
        'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- quadkey

def quadkey(lat, lon, z=ZOOM):
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 1 << z
    x = int((lon + 180.0) / 360.0 * n)
    s = math.sin(math.radians(lat))
    y = int((0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n)
    x = max(0, min(n - 1, x)); y = max(0, min(n - 1, y))
    out = []
    for i in range(z, 0, -1):
        d, mask = 0, 1 << (i - 1)
        if x & mask: d += 1
        if y & mask: d += 2
        out.append(str(d))
    return ''.join(out)


# ---------------------------------------------------------------- the chip

def chm_chip(lat, lng, pad_m=2000.0):
    """A height raster over one course, plus a lat/lon -> pixel mapper.

    Reports what it found rather than assuming: the model's CRS, resolution
    and nodata all come off the file, because guessing any of them is how you
    end up measuring the wrong thing confidently.
    """
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.warp import transform as warp_transform

    qk = quadkey(lat, lng)
    dlat = pad_m / 110540.0
    dlon = pad_m / (111320.0 * math.cos(math.radians(lat)))
    errs = []
    for tag, tmpl in SOURCES:
        url = '/vsicurl/' + (tmpl % qk)
        try:
            with rasterio.open(url) as ds:
                crs = ds.crs
                lons = [lng - dlon, lng + dlon, lng + dlon, lng - dlon]
                lats = [lat - dlat, lat - dlat, lat + dlat, lat + dlat]
                xs, ys = warp_transform('EPSG:4326', crs, lons, lats)
                win = from_bounds(min(xs), min(ys), max(xs), max(ys), ds.transform)
                fill = ds.nodata if ds.nodata is not None else 0
                arr = ds.read(1, window=win, boundless=True, fill_value=fill)
                wt = ds.window_transform(win)
                info = {'source': tag, 'quadkey': qk, 'crs': str(crs),
                        'dtype': ds.dtypes[0], 'nodata': ds.nodata,
                        'tile_px': [ds.width, ds.height],
                        # where the window sits on the tile. A course near a
                        # tile edge reads past it, and boundless=True fills
                        # that with nodata -- which must not be mistaken for
                        # measured open ground.
                        'win': [float(win.col_off), float(win.row_off),
                                float(win.width), float(win.height)],
                        'window_px': [int(arr.shape[1]), int(arr.shape[0])]}
                nod = ds.nodata

            a = arr.astype('float32')
            if nod is not None:
                a[arr == nod] = np.nan

            # Ground resolution, worked out from the file rather than assumed:
            # 4326 is degrees, 3857 is inflated mercator metres, anything else
            # (UTM and friends) is already true metres.
            epsg = crs.to_epsg()
            px = abs(wt.a)
            if epsg == 4326:
                m_per_px = px * 111320.0 * math.cos(math.radians(lat))
            elif epsg == 3857:
                m_per_px = px * math.cos(math.radians(lat))
            else:
                m_per_px = px
            info['m_per_px'] = round(float(m_per_px), 3)

            # A local affine, fitted once from three reference points. Over
            # 2.6km the projection is linear to well under a metre, and this
            # keeps the probe loop to arithmetic instead of a pyproj call per
            # sample (roughly 16,000 of them per course).
            rlat = [lat, lat + dlat, lat]
            rlon = [lng, lng, lng + dlon]
            RX, RY = warp_transform('EPSG:4326', crs, rlon, rlat)
            c0 = (RX[0] - wt.c) / wt.a
            r0 = (RY[0] - wt.f) / wt.e
            dc_dlat = ((RX[1] - wt.c) / wt.a - c0) / dlat
            dr_dlat = ((RY[1] - wt.f) / wt.e - r0) / dlat
            dc_dlon = ((RX[2] - wt.c) / wt.a - c0) / dlon
            dr_dlon = ((RY[2] - wt.f) / wt.e - r0) / dlon

            def to_px(la, lo):
                dla, dlo = la - lat, lo - lng
                return (c0 + dc_dlat * dla + dc_dlon * dlo,
                        r0 + dr_dlat * dla + dr_dlon * dlo)

            # prove the affine against the real projection at a far corner
            cx, cy = to_px(lat + dlat, lng + dlon)
            TX, TY = warp_transform('EPSG:4326', crs, [lng + dlon], [lat + dlat])
            ex = abs(cx - (TX[0] - wt.c) / wt.a) * m_per_px
            ey = abs(cy - (TY[0] - wt.f) / wt.e) * m_per_px
            info['affine_err_m'] = round(float(max(ex, ey)), 3)
            return a, to_px, info
        except Exception as e:
            errs.append(f'{tag}: {type(e).__name__}: {str(e)[:110]}')
    raise RuntimeError(f'no canopy tile for {qk} :: ' + ' | '.join(errs))


# ---------------------------------------------------------------- masks

ROUGH_M = 1.0       # local height spread that separates a crown from a roof
ROUGH_K = 7         # window, px (~7 m)


def _boxsum(a, k):
    """Summed-area box filter -- O(1) per pixel regardless of window."""
    import numpy as np
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0))), 0), 1)
    p = k // 2
    c = np.pad(c, ((p, p + 1), (p, p + 1)), mode='edge')
    H, W = a.shape
    return c[k:k+H, k:k+W] - c[0:H, k:k+W] - c[k:k+H, 0:W] + c[0:H, 0:W]


def masked_rough(h, tall, k=ROUGH_K):
    """Local height spread computed over TALL pixels only.

    A building is flat on top and a tree crown is not, so height roughness
    separates them -- but only if the window ignores the ground. Measured
    naively, a roof's EDGE is the roughest thing on the chip (a twelve-metre
    step in one pixel) and a third of every roof survives. Masking the window
    to tall pixels means an edge pixel sees roof, not the drop: on a synthetic
    scene of crowns and slabs this keeps 100% of canopy and 2.5% of roofs.
    """
    import numpy as np
    m = tall.astype('float64')
    hm = np.nan_to_num(h, nan=0.0) * m
    n = np.maximum(_boxsum(m, k), 1.0)
    s1 = _boxsum(hm, k)
    s2 = _boxsum(hm * hm, k)
    return np.sqrt(np.maximum(s2 / n - (s1 / n) ** 2, 0.0))


def tree_masks(hgt):
    """-> {'raw': tall, 'flat': tall minus flat-topped ground}, plus stats."""
    import numpy as np
    tall = np.isfinite(hgt) & (hgt >= TREE_M)
    rough = masked_rough(hgt, tall)
    flat = tall & (rough >= ROUGH_M)
    dropped = tall & ~flat
    return ({'raw': tall, 'flat': flat},
            {'tall_px': int(tall.sum()), 'flat_px': int(flat.sum()),
             'dropped_px': int(dropped.sum()),
             'dropped_pct': (round(100.0 * float(dropped.sum()) / max(1, int(tall.sum())), 1))},
            dropped)


def building_raster(buildings_ll, to_px, shape):
    """OSM building footprints burned into the chip grid.

    Written to validate the roughness filter; it outlived it. Since the
    filter failed (see sampler below) these footprints ARE the building
    removal, which only works with osm.py's cap raised off 60.
    """
    import numpy as np
    from PIL import Image, ImageDraw
    H, W = shape
    im = Image.new('1', (W, H), 0)
    d = ImageDraw.Draw(im)
    n = 0
    for g in buildings_ll:
        pts = [to_px(p[0], p[1]) for p in g]
        if len(pts) >= 3:
            d.polygon([(float(x), float(y)) for x, y in pts], fill=1)
            n += 1
    return np.array(im, dtype=bool), n


# ---------------------------------------------------------------- sampler

CANOPY_PAD_M = 2400.0   # osm.py fetches a 2.2km box; the chip must cover it
BLDG_DILATE = 3         # px -- roof overhang, and OSM footprints are drawn tight

# A tree that changes how a hole is played, as opposed to anything over 3m.
# Measured on five Long Island courses at TREE_M: two thirds of all hole sides
# reported timber inside 15 yards of the centreline and half of everything
# piled onto the very first probe at 10 yards. A fairway is 30-40 yards wide,
# so that distribution is not golf -- it is rough, scrub, mounding and young
# growth clearing a three-metre bar. Eight metres is about twenty-six feet:
# tall enough that you have to go over it or around it.
CANOPY_M = 8.0
# ...and it has to be a crown, not a pixel. A tall pixel counts only if most of
# its 5x5 neighbourhood is tall too, which is an opening: speckle and hedgerows
# one pixel wide fall out, a real canopy does not.
CANOPY_WIN = 5
CANOPY_MIN = 15         # of 25


def _dilate(b, k):
    """Grow a boolean mask by k pixels. Shifts, not a summed-area table --
    a float64 cumsum over a 4800px chip costs 185MB a copy."""
    out = b
    for _ in range(k):
        n = out.copy()
        n[1:, :] |= out[:-1, :]
        n[:-1, :] |= out[1:, :]
        n[:, 1:] |= out[:, :-1]
        n[:, :-1] |= out[:, 1:]
        out = n
    return out


class Canopy:
    """A measured tree mask over one course, asked one point at a time."""

    __slots__ = ('mask', 'valid', 'to_px', 'info')

    def __init__(self, mask, valid, to_px, info):
        self.mask, self.valid = mask, valid
        self.to_px, self.info = to_px, info

    def tall(self, lat, lon):
        """True, False, or None for 'not measured here'.

        None is not False. A point the model does not cover has not been
        measured, and calling it open ground is exactly the mistake that had
        Bobby Jones come back treeless on the first harness run. Off the
        array and inside-but-unmeasured (nodata, or window fill from past
        the tile edge) both answer None.
        """
        c, r = self.to_px(lat, lon)
        c, r = int(round(c)), int(round(r))
        v = self.valid
        if 0 <= r < v.shape[0] and 0 <= c < v.shape[1] and v[r, c]:
            return bool(self.mask[r, c])
        return None


def sampler(lat, lng, feats=None, pad_m=CANOPY_PAD_M):
    """The GEN 10 tree source: everything over 3m, minus mapped buildings.

    The roughness filter this file uses for review is deliberately NOT used
    here. Measured against eight real courses it dropped only 7.7-19.4% of
    the tall pixels standing on a mapped building footprint while removing
    16-52% of ALL tall pixels -- it was eating smooth canopy interior, not
    roofs. A roof in a canopy height model is a noisy blob rather than the
    clean slab the synthetic scene had, so texture cannot separate the two.
    Geometry can, so OSM footprints are burned out instead.
    """
    import numpy as np
    hgt, to_px, info = chm_chip(lat, lng, pad_m=pad_m)
    valid = np.isfinite(hgt)
    # Pixels the window took from beyond the tile edge are fill, not ground.
    c0, r0 = info['win'][0], info['win'][1]
    TW, TH = info['tile_px']
    rows, cols = valid.shape
    rr = np.arange(rows) + r0
    cc = np.arange(cols) + c0
    valid[(rr < 0) | (rr >= TH), :] = False
    valid[:, (cc < 0) | (cc >= TW)] = False
    mask = valid & (hgt >= CANOPY_M)
    del hgt
    info['valid_pct'] = round(100.0 * float(valid.mean()), 1)
    info['tall_px'] = int(mask.sum())
    # the opening: keep only pixels that sit inside a crown
    solid = _boxsum(mask.astype('float64'), CANOPY_WIN) >= CANOPY_MIN
    mask &= solid
    info['crown_px'] = int(mask.sum())
    info['speckle_dropped_pct'] = (
        round(100.0 * (1 - info['crown_px'] / max(1, info['tall_px'])), 1))
    bld = [g for t, g in (feats or []) if t == 'u']
    info['buildings'] = len(bld)
    if bld:
        braster, nb = building_raster(bld, to_px, mask.shape)
        if nb:
            braster = _dilate(braster, BLDG_DILATE)
            info['building_px_cut'] = int((mask & braster).sum())
            mask &= ~braster
    info['tree_px'] = int(mask.sum())
    return Canopy(mask, valid, to_px, info)


# ---------------------------------------------------------------- geometry

def project_yd(pts_ll, lat0, lon0):
    k = math.cos(math.radians(lat0)) * 121740.0
    return [((p[1] - lon0) * k, -(p[0] - lat0) * 121740.0) for p in pts_ll]


def wood_gap(mask, to_px, line_ll, lat0, lon0):
    """For each hole: how far off the line, each side, does timber start?

    The same question generate.PROBES asks of OSM, asked of the height model
    instead. Returns per-side first-timber distance in yards, and the share of
    the walk that has timber inside 60 yards -- which is what a chute is."""
    line = project_yd(line_ll, lat0, lon0)
    total = sum(math.hypot(line[i+1][0]-line[i][0], line[i+1][1]-line[i][1])
                for i in range(len(line)-1))
    if total < 60:
        return None

    def at(a):
        cum = 0.0
        for i in range(len(line)-1):
            L = math.hypot(line[i+1][0]-line[i][0], line[i+1][1]-line[i][1])
            if cum + L >= a and L:
                t = (a-cum)/L
                return (line[i][0]+t*(line[i+1][0]-line[i][0]),
                        line[i][1]+t*(line[i+1][1]-line[i][1]),
                        (line[i+1][0]-line[i][0])/L, (line[i+1][1]-line[i][1])/L)
            cum += L
        x, y = line[-1]
        return (x, y, 0.0, -1.0)

    def yd_to_ll(x, y):
        k = math.cos(math.radians(lat0)) * 121740.0
        return (lat0 - y / 121740.0, lon0 + x / k)

    def tall(x, y):
        la, lo = yd_to_ll(x, y)
        c, r = to_px(la, lo)
        c, r = int(round(c)), int(round(r))
        if not (0 <= r < mask.shape[0] and 0 <= c < mask.shape[1]):
            return None
        return bool(mask[r, c])

    firsts = {-1: None, 1: None}
    chute = 0
    steps = 0
    oob = 0
    a = 10.0
    while a <= total - 10.0:
        x, y, dx, dy = at(a)
        steps += 1
        near = 0
        for side in (-1, 1):
            for d in PROBES:
                q = (x - dy*side*d, y + dx*side*d)
                t = tall(*q)
                if t is None:
                    oob += 1
                if t:
                    if firsts[side] is None or d < firsts[side]:
                        firsts[side] = d
                    if d <= 60:
                        near += 1
                    break
        if near == 2:
            chute += 1
        a += 12.0
    # A hole that falls off the edge of the height chip has not been measured
    # and must not be reported as treeless -- that is how Bobby Jones came
    # back with 32 holes and a 0% median chute on the first run: OSM fetches a
    # 2.2km radius, so outlying holes from the neighbouring course sat outside
    # the raster and scored as open ground.
    if oob > 0.30 * steps * 2:
        return None
    return {'total': round(total), 'left': firsts[-1], 'right': firsts[1],
            'chute_pct': round(100.0 * chute / max(1, steps))}


# ---------------------------------------------------------------- output

def mask_png(hgt, tall):
    """A tree mask as a transparent PNG data URI.

    A 4km chip at 1m is sixteen million pixels; drawing them as SVG rectangles
    would be absurd. An image is exact and small.
    """
    import base64, io
    import numpy as np
    from PIL import Image
    h = np.nan_to_num(hgt, nan=0.0)
    rgba = np.zeros(h.shape + (4,), dtype='uint8')
    # ramp the green with height so a hedge and an oak do not look alike
    k = np.clip((h - TREE_M) / 22.0, 0, 1)
    rgba[..., 0] = (20 + 20 * (1 - k)).astype('uint8')
    rgba[..., 1] = (90 + 70 * (1 - k)).astype('uint8')
    rgba[..., 2] = (40 + 30 * (1 - k)).astype('uint8')
    rgba[..., 3] = np.where(tall, (110 + 110 * k).astype('uint8'), 0)
    buf = io.BytesIO()
    Image.fromarray(rgba, 'RGBA').save(buf, format='PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


PAGE_CSS = """
body{margin:0;background:#F2F1EC;color:#0C1710;font-family:Archivo,system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:40px 20px 80px}
h1{font-family:Fraunces,Georgia,serif;font-size:32px;margin:0 0 6px;letter-spacing:-.015em}
p.dek{color:#6D7770;max-width:76ch;margin:0 0 20px;font-size:15px;line-height:1.6}
table{border-collapse:collapse;font-size:13.5px;background:#fff;border:1px solid #E3E3DC;margin:0 0 22px}
th,td{padding:7px 13px;border-bottom:1px solid #EEEEE8;text-align:left}
th{font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:#6D7770}
td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.chute td{background:#F2F7EE}
.stage{position:relative;aspect-ratio:1;border:1px solid #E3E3DC;border-radius:3px;
 overflow:hidden;background:#0C1710}
.stage img{position:absolute;inset:0;width:100%;height:100%}
.stage img.m{image-rendering:pixelated}
.stage svg{position:absolute;inset:0;width:100%;height:100%}
.hl{stroke:#C7F24A;stroke-width:2.2;fill:none;opacity:.95}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}
figcaption{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:#6D7770;
 margin:0 0 6px;font-weight:600}
figure{margin:0}
@media(max-width:820px){.pair{grid-template-columns:1fr}}
"""


def one(key):
    import osm
    from generate import _match_course_holes
    q = urllib.parse.quote(key, safe='')
    course = (_get(f'courses?select=key,name,info,market_key&key=eq.{q}') or [{}])[0]
    if not course:
        return {'key': key, 'error': 'no such course'}
    info = course.get('info') or {}
    lat, lng = info.get('lat'), info.get('lng')
    if lat is None or lng is None:
        return {'key': key, 'error': 'no coordinates'}
    name = course.get('name') or key

    hgt, to_px, meta = chm_chip(lat, lng)
    masks, mstat, dropped = tree_masks(hgt)
    print(f'[{key}] {meta} {mstat}', flush=True)

    feats = osm.fetch_course(key, name, course.get('market_key') or '', lat, lng)
    # Same hole filter build_course uses. Without it a course inherits its
    # neighbours' holes: Bobby Jones, a nine, came back with 32.
    raw_holes = [h for h in (feats or {}).get('h') or []
                 if str(h.get('r', '')).isdigit()]
    holes = _match_course_holes(raw_holes, name)
    holes.sort(key=lambda h: int(h['r']))

    bld = [g for t, g in ((feats or {}).get('f') or []) if t == 'u']
    braster, nb = building_raster(bld, to_px, hgt.shape)
    import numpy as np
    hit = int((dropped & braster).sum())
    mstat['osm_buildings'] = nb
    mstat['dropped_on_osm_building_pct'] = (
        round(100.0 * hit / max(1, mstat['dropped_px']), 1) if nb else None)
    mstat['osm_building_px_dropped_pct'] = (
        round(100.0 * hit / max(1, int((braster & masks['raw']).sum())), 1) if nb else None)

    out = {}
    for tag, m in masks.items():
        rows = []
        for h in holes:
            ll = h.get('l') or []
            if len(ll) < 2:
                continue
            g = wood_gap(m, to_px, ll, ll[0][0], ll[0][1])
            if not g:
                continue
            g['ref'] = str(h.get('r') or '?')
            rows.append(g)
        rows.sort(key=lambda r: (len(r['ref']), r['ref']))
        out[tag] = rows

    def summ(rows):
        if not rows:
            return {'holes': 0, 'timber': 0, 'both': 0, 'chute': None}
        return {'holes': len(rows),
                'timber': sum(1 for r in rows
                              if r['left'] is not None or r['right'] is not None),
                'both': sum(1 for r in rows
                            if r['left'] is not None and r['right'] is not None),
                'chute': sorted(r['chute_pct'] for r in rows)[len(rows) // 2]}

    finite = hgt[np.isfinite(hgt)]
    row = {'key': key, 'name': name, 'lat': lat, 'lng': lng,
           'source': meta['source'], 'm_per_px': meta['m_per_px'],
           'affine_err_m': meta.get('affine_err_m'),
           'tall_pct': round(100.0 * float((finite >= TREE_M).mean()), 1) if finite.size else None,
           'raw': summ(out['raw']), 'flat': summ(out['flat'])}
    row.update({k: v for k, v in mstat.items() if k != 'tall_px'})
    write_page(key, name, lat, lng, hgt, to_px, meta, holes, out, row, masks, mstat)
    print(f'  {key:<40} raw chute {row["raw"]["chute"]}%  ->  flat chute '
          f'{row["flat"]["chute"]}%   (dropped {mstat["dropped_pct"]}% of tall px, '
          f'{mstat["dropped_on_osm_building_pct"]}% of those on an OSM building)',
          flush=True)
    return row


def write_page(key, name, lat, lng, hgt, to_px, meta, holes, out, summary,
               masks, mstat):
    import naip
    pad_m = 2000.0
    dlat = pad_m / 110540.0
    dlon = pad_m / (111320.0 * math.cos(math.radians(lat)))
    bb = (lng - dlon, lat - dlat, lng + dlon, lat + dlat)
    aer = (f'{naip.SERVER}?bbox={bb[0]},{bb[1]},{bb[2]},{bb[3]}'
           f'&bboxSR=4326&imageSR=4326&size=1200,1200&format=jpg&f=image')
    H, W = hgt.shape

    def vb(la, lo):
        c, r = to_px(la, lo)
        return 1000.0 * c / W, 1000.0 * r / H

    paths = []
    for h in holes:
        ll = h.get('l') or []
        if len(ll) >= 2:
            pts = ' '.join(f'{x:.1f},{y:.1f}'
                           for x, y in (vb(p[0], p[1]) for p in ll))
            paths.append(f'<polyline class="hl" points="{pts}"/>')
    lines = ''.join(paths)

    panes = []
    for tag, cap in (('raw', 'everything over 3 m'),
                     ('flat', 'flat-topped ground removed')):
        panes.append(
            f'<figure><figcaption>{cap}</figcaption><div class="stage">'
            f'<img src="{aer}" alt=""><img class="m" src="{mask_png(hgt, masks[tag])}" alt="">'
            f'<svg viewBox="0 0 1000 1000">{lines}</svg></div></figure>')

    def table(rows):
        return ''.join(
            f'<tr class="{"chute" if r["chute_pct"] >= 60 else ""}">'
            f'<td>{r["ref"]}</td><td class="n">{r["total"]}</td>'
            f'<td class="n">{"&mdash;" if r["left"] is None else int(r["left"])}</td>'
            f'<td class="n">{"&mdash;" if r["right"] is None else int(r["right"])}</td>'
            f'<td class="n">{r["chute_pct"]}%</td></tr>' for r in rows)

    byref = {r['ref']: r for r in out['flat']}
    both = ''.join(
        f'<tr class="{"chute" if byref.get(r["ref"], r)["chute_pct"] >= 60 else ""}">'
        f'<td>{r["ref"]}</td><td class="n">{r["total"]}</td>'
        f'<td class="n">{r["chute_pct"]}%</td>'
        f'<td class="n">{byref.get(r["ref"], {}).get("chute_pct", "&mdash;")}%</td>'
        f'<td class="n">{"&mdash;" if byref.get(r["ref"], {}).get("left") is None else int(byref[r["ref"]]["left"])}</td>'
        f'<td class="n">{"&mdash;" if byref.get(r["ref"], {}).get("right") is None else int(byref[r["ref"]]["right"])}</td>'
        f'</tr>' for r in out['raw'])

    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Tree cover &mdash; {name}</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600'
            '&family=Archivo:wght@400;600&display=swap" rel="stylesheet">'
            f'<style>{PAGE_CSS}</style></head><body><div class="wrap">'
            f'<h1>Tree cover &mdash; {name}</h1>'
            f'<p class="dek">Measured tree height from the WRI/Meta model '
            f'({meta["source"]}, {meta["m_per_px"]} m/px). A building is as tall as an '
            f'oak and reads the same to a height model, so the right pane drops ground '
            f'whose top is flat: local height spread under {ROUGH_M:g} m across a '
            f'{ROUGH_K}-pixel window, measured over tall pixels only so a roof edge sees '
            f'roof rather than the drop to the ground. The number that matters is whether '
            f'the chute figures survive that filter &mdash; if they collapse, we were '
            f'drawing houses.</p>'
            '<table><tbody>'
            f'<tr><th>Ground over {TREE_M:g}m</th><td class="n">{summary["tall_pct"]}%</td></tr>'
            f'<tr><th>Dropped as flat-topped</th><td class="n">{mstat["dropped_pct"]}% of tall pixels</td></tr>'
            f'<tr><th>&hellip; of which on an OSM building</th><td class="n">{mstat["dropped_on_osm_building_pct"]}%</td></tr>'
            f'<tr><th>OSM building pixels dropped</th><td class="n">{mstat["osm_building_px_dropped_pct"]}% (of {mstat["osm_buildings"]} mapped)</td></tr>'
            f'<tr><th>Median chute</th><td class="n">{summary["raw"]["chute"]}% &rarr; '
            f'<b>{summary["flat"]["chute"]}%</b></td></tr>'
            f'<tr><th>Holes</th><td class="n">{summary["flat"]["holes"]}</td></tr>'
            f'<tr><th>Affine error</th><td class="n">{meta.get("affine_err_m")} m</td></tr>'
            '</tbody></table>'
            f'<div class="pair">{"".join(panes)}</div>'
            '<h1 style="font-size:20px;margin:32px 0 8px">Per hole</h1>'
            '<p class="dek">Chute is the share of the walk with timber inside 60 yards on '
            '<em>both</em> sides. Left and right are first timber in yards, after the '
            'flat-topped filter.</p>'
            '<table><thead><tr><th>Hole</th><th>Yards</th><th>Chute raw</th>'
            '<th>Chute filtered</th><th>Left</th><th>Right</th></tr></thead>'
            f'<tbody>{both}</tbody></table>'
            '</div></body></html>')
    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    open(os.path.join(ROOT, 'demo', f'chm_{key}.html'), 'w').write(html)


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: chm.py <course_key>[,<course_key>...]')
    keys = [k.strip() for k in sys.argv[1].split(',') if k.strip()]
    rows = []
    for k in keys:
        try:
            rows.append(one(k))
        except Exception as e:
            print(f'  [{k}] FAILED: {type(e).__name__}: {e}', flush=True)
            rows.append({'key': k, 'error': f'{type(e).__name__}: {str(e)[:160]}'})
    good = [r for r in rows if not r.get('error')]
    if not good:
        sys.exit('every course failed')

    def cell(v, s='%'):
        return '&mdash;' if v is None else f'{v}{s}'
    trs = ''.join(
        (f'<tr><td>{r["key"]}</td><td colspan="8">{r["error"]}</td></tr>'
         if r.get('error') else
         f'<tr><td><a href="chm_{r["key"]}.html">{r["name"]}</a></td>'
         f'<td class="n">{r["m_per_px"]}</td>'
         f'<td class="n">{cell(r["tall_pct"])}</td>'
         f'<td class="n">{r["flat"]["holes"]}</td>'
         f'<td class="n">{r["flat"]["timber"]}</td>'
         f'<td class="n">{r["flat"]["both"]}</td>'
         f'<td class="n">{cell(r["raw"]["chute"])}</td>'
         f'<td class="n"><b>{cell(r["flat"]["chute"])}</b></td>'
         f'<td class="n">{cell(r["dropped_pct"])}</td>'
         f'<td class="n">{cell(r["dropped_on_osm_building_pct"])}</td></tr>')
        for r in rows)
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Tree cover review</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600'
            '&family=Archivo:wght@400;600&display=swap" rel="stylesheet">'
            f'<style>{PAGE_CSS}</style></head><body><div class="wrap">'
            '<h1>Tree cover review</h1>'
            '<p class="dek">Measured canopy height per course, before and after dropping '
            'flat-topped ground. <b>Chute</b> is the share of the median hole with timber '
            'inside 60 yards on both sides &mdash; the number that says whether a hole plays '
            'as a corridor. The pair to read is <b>raw</b> against <b>filtered</b>: if a '
            'course collapses, its trees were roofs. <b>On OSM bldg</b> is the share of '
            'dropped pixels that land on a mapped building footprint, which is the check '
            'that the filter is removing what we think it is &mdash; partial only, because '
            'osm.py caps buildings at 60 a course.</p>'
            '<table><thead><tr><th>Course</th><th>m/px</th><th>Over 3m</th><th>Holes</th>'
            '<th>Timber</th><th>Both</th><th>Chute raw</th><th>Chute filtered</th>'
            '<th>Dropped</th><th>On OSM bldg</th></tr></thead>'
            f'<tbody>{trs}</tbody></table></div></body></html>')
    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    open(os.path.join(ROOT, 'demo', 'chm_index.html'), 'w').write(html)
    print(f'wrote demo/chm_index.html ({len(good)} of {len(rows)} ok)', flush=True)


if __name__ == '__main__':
    main()
