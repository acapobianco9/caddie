#!/usr/bin/env python3
"""NAIP imagery stage for the Caddie sweep (stage 2.5).

Pulls one USDA NAIP aerial chip per course from the USGS ImageServer
(public-domain imagery, no key required) and mines it for what
OpenStreetMap is missing:

  SAND  'B' features — bunker candidates detected as bright, low-NDVI
        blobs. generate.py only uses them on holes that have a green but
        no surveyed sand (OSM always wins) and flags the pack naip_sand,
        so the render and the app can say where the data came from.
  TURF  the irrigated ground, as a set of ~22 m discs, plus `arid`: how
        much of everything OUTSIDE the turf is bare and bright. That one
        number is the difference between a parkland course and a desert
        one, measured off the imagery rather than inferred from the zip
        code (GEN 7).
  VOTE  a turf scorer the synthesizer uses to break ties between rival
        green candidates: a real green sits on smooth, healthy turf; a
        neighbour-course impostor in the scrub does not.

Calibration comes from ground-truth probes against Bethpage's surveyed
features (Aug 2026): sand recall ~1/3 per bunker at a hard site (grass-
faced bunkers, leaf-on imagery) with ~13 yd placement accuracy — enough
to give most sand-less holes at least one real bunker, not enough to
claim a complete map, hence the flags. Turf scoring separated real green
sites from scrub in the same probes.

Best-effort by design: any failure returns None and the sweep proceeds
OSM-only. Needs pillow + numpy (installed by the workflow).
"""
import io, math, urllib.request
from collections import deque

SERVER = ('https://imagery.nationalmap.gov/arcgis/rest/services/'
          'USGSNAIPPlus/ImageServer/exportImage')
ELEV = ('https://elevation.nationalmap.gov/arcgis/rest/services/'
        '3DEPElevation/ImageServer/exportImage')
UA = 'YoinkCaddie/1.0 (NAIP stage; contact: anthony@amg-demolition.com)'
PAD_M = 1250.0     # chip half-width in meters (covers a full course)
SIZE = 2600        # export pixels (~1 m/px at this pad)
G = 3              # analysis grid stride in pixels
GT = 22            # turf-mask cell in pixels (~22 m)
DEM = 500          # DEM export pixels (~5 m/px at this pad)


def _fetch(lat, lng):
    import numpy as np
    from PIL import Image
    pady = PAD_M / 110540.0
    padx = PAD_M / (111320.0 * math.cos(math.radians(lat)))
    bbox = (lng - padx, lat - pady, lng + padx, lat + pady)
    url = (f'{SERVER}?bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'
           f'&bboxSR=4326&imageSR=4326&size={SIZE},{SIZE}'
           f'&bandIds=3,0,1&format=png&f=image')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    a = np.asarray(im, dtype=np.float32)
    return a[:, :, 0], a[:, :, 1], bbox      # NIR band, Red band


def _blobs(mask):
    """4-connected components over a boolean grid (sparse-friendly BFS)."""
    import numpy as np
    h, w = mask.shape
    lab = np.zeros((h, w), dtype=np.int32)
    out = []
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if lab[y0, x0]:
            continue
        idx = len(out) + 1
        q = deque([(y0, x0)])
        lab[y0, x0] = idx
        cells = []
        while q:
            y, x = q.popleft()
            cells.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = idx
                    q.append((ny, nx))
        out.append(cells)
    return out


def _hull(pts):
    """Convex hull (monotone chain) — bunker outline good enough to draw."""
    pts = sorted(set(pts))
    if len(pts) <= 3:
        return pts
    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) -
                                   (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h
    lo = half(pts)
    hi = half(reversed(pts))
    return lo[:-1] + hi[:-1]


def _boxmean(a, k):
    """Mean of a (2k+1) square window, via an integral image. numpy only —
    the sweep installs pillow and numpy and nothing else."""
    import numpy as np
    p = np.pad(a, k, mode='edge').astype(np.float64)
    c = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    n = 2 * k + 1
    H, W = a.shape
    s = (c[n:n + H, n:n + W] - c[0:H, n:n + W]
         - c[n:n + H, 0:W] + c[0:H, 0:W])
    return (s / (n * n)).astype(np.float32)


def _ridges(z, mpx, tpi_lo, relief_lo, kind, cap):
    """Crest lines of raised ground.

    z is a DEM in metres, mpx metres per pixel. A cell is on a ridge when it
    stands `tpi_lo` metres above the mean of the ground around it — the same
    thing your eye does when it picks a dune out of a links.
    """
    import numpy as np
    win = max(3, int(round(65.0 / mpx)))
    tpi = z - _boxmean(z, win)
    m = tpi > tpi_lo
    # a whole mountainside is not a dune: back off until the mask is sane
    lo = tpi_lo
    for _ in range(6):
        if m.mean() <= 0.12:
            break
        lo *= 1.5
        m = tpi > lo
    if m.mean() > 0.12 or not m.any():
        return []
    return _crests(m, z, mpx, relief_lo, kind, cap, 900, 90000)


def _scarps(z, mpx, slope_lo, relief_lo, cap):
    """Crest lines of steep ground — the top edge of a bluff.

    A cliff is not a raised blob, so TPI finds the whole plateau behind it and
    nothing useful. Gradient does find it, and the top of the band is the line
    you actually stand on.
    """
    import numpy as np
    gy, gx = np.gradient(z.astype(np.float32), mpx)
    g = np.hypot(gx, gy)
    m = g > slope_lo
    lo = slope_lo
    for _ in range(5):
        if m.mean() <= 0.10:
            break
        lo *= 1.4
        m = g > lo
    if m.mean() > 0.10 or not m.any():
        return []
    return _crests(m, z, mpx, relief_lo, 'scarp', cap, 1200, 260000)


def _crests(m, z, mpx, relief_lo, kind, cap, a_lo, a_hi):
    """Each connected blob of `m` reduced to a five-point crest along its own
    long axis, plus a point 30 m down the fall so the renderer can hachure the
    correct side whatever direction the hole runs."""
    import numpy as np
    out = []
    cell = mpx * mpx
    for cells in _blobs(m):
        a2 = len(cells) * cell
        if not a_lo <= a2 <= a_hi:
            continue
        ys = np.array([c[0] for c in cells], dtype=np.float32)
        xs = np.array([c[1] for c in cells], dtype=np.float32)
        zz = np.array([z[c[0], c[1]] for c in cells], dtype=np.float32)
        if float(zz.max() - zz.min()) < relief_lo:
            continue
        cy, cx = float(ys.mean()), float(xs.mean())
        dy, dx = ys - cy, xs - cx
        # principal axis of the blob = the line the crest runs along
        cov = np.array([[float((dx * dx).mean()), float((dx * dy).mean())],
                        [float((dx * dy).mean()), float((dy * dy).mean())]])
        w, v = np.linalg.eigh(cov)
        ax = v[:, int(np.argmax(w))]              # (x, y) unit-ish
        n = math.hypot(float(ax[0]), float(ax[1])) or 1.0
        ax = (float(ax[0]) / n, float(ax[1]) / n)
        t = dx * ax[0] + dy * ax[1]
        if float(t.max() - t.min()) * mpx < 30.0:
            continue                              # a knob, not a ridge
        crest = []
        edges = np.linspace(float(t.min()), float(t.max()), 6)
        for i in range(5):
            sel = (t >= edges[i]) & (t <= edges[i + 1])
            if not sel.any():
                continue
            k = int(np.argmax(np.where(sel, zz, -1e9)))
            crest.append((float(ys[k]), float(xs[k])))
        if len(crest) < 3:
            continue
        # the fall: 30 m off the crest, on whichever side drops away
        off = 30.0 / mpx
        px, py = -ax[1], ax[0]
        H, W = z.shape
        def zat(fy, fx):
            iy, ix = int(round(fy)), int(round(fx))
            return float(z[iy, ix]) if 0 <= iy < H and 0 <= ix < W else 1e9
        side = 1.0 if zat(cy + py * off, cx + px * off) <= zat(cy - py * off, cx - px * off) else -1.0
        out.append({'k': kind, 'h': round(float(zz.max() - zz.min()), 1),
                    'c': crest,
                    'f': (cy + py * off * side, cx + px * off * side)})
        if len(out) >= cap:
            break
    return out


def terrain(lat, lng):
    """One 3DEP chip -> (sampler, ridges), or (None, []) on any failure.

    The sampler is the per-point elevation lookup facts.elev_ft already uses;
    the ridges are dune crests and coastal scarps, which OSM almost never maps
    even on courses that are nothing but dunes.
    """
    try:
        import numpy as np
        from PIL import Image
        pady = PAD_M / 110540.0
        padx = PAD_M / (111320.0 * math.cos(math.radians(lat)))
        bbox = (lng - padx, lat - pady, lng + padx, lat + pady)
        url = (f'{ELEV}?bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'
               f'&bboxSR=4326&imageSR=4326&size={DEM},{DEM}&format=tiff&f=image')
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        im = Image.open(io.BytesIO(raw))
        a = np.asarray(im, dtype=np.float32)
        if a.ndim == 3:
            a = a[:, :, 0]
        H, W = a.shape

        def sample(pt):
            x = int((pt[1] - bbox[0]) / (bbox[2] - bbox[0]) * W)
            y = int((bbox[3] - pt[0]) / (bbox[3] - bbox[1]) * H)
            if not (0 <= x < W and 0 <= y < H):
                return None
            v = float(a[y, x])
            return v if -400 < v < 9000 else None
    except Exception:
        return None, []
    try:
        z = np.where((a > -400) & (a < 9000), a, np.nan)
        if not np.isfinite(z).all():
            z = np.nan_to_num(z, nan=float(np.nanmedian(z)) if np.isfinite(z).any() else 0.0)
        mpx = (bbox[3] - bbox[1]) * 110540.0 / H
        rid = (_ridges(z, mpx, 1.6, 2.5, 'dune', 26)
               + _scarps(z, mpx, 0.25, 10.0, 10))

        def ll(fy, fx):
            return [round(bbox[3] - fy / H * (bbox[3] - bbox[1]), 6),
                    round(bbox[0] + fx / W * (bbox[2] - bbox[0]), 6)]
        out = [{'k': r['k'], 'h': r['h'],
                'c': [ll(y, x) for y, x in r['c']],
                'f': ll(*r['f'])} for r in rid]
        return sample, out
    except Exception:
        return sample, []


def elevation_sampler(lat, lng):
    """Back-compatible wrapper: just the elevation lookup."""
    return terrain(lat, lng)[0]


def _elevation_sampler_unused(lat, lng):
    """Superseded by terrain(); kept only as the reference implementation of
    the single-purpose DEM fetch."""
    try:
        import numpy as np
        from PIL import Image
        pady = PAD_M / 110540.0
        padx = PAD_M / (111320.0 * math.cos(math.radians(lat)))
        bbox = (lng - padx, lat - pady, lng + padx, lat + pady)
        url = (f'{ELEV}?bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'
               f'&bboxSR=4326&imageSR=4326&size=500,500&format=tiff&f=image')
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
        im = Image.open(io.BytesIO(raw))
        a = np.asarray(im, dtype=np.float32)
        if a.ndim == 3:
            a = a[:, :, 0]
        H, W = a.shape

        def sample(pt):
            x = int((pt[1] - bbox[0]) / (bbox[2] - bbox[0]) * W)
            y = int((bbox[3] - pt[0]) / (bbox[3] - bbox[1]) * H)
            if not (0 <= x < W and 0 <= y < H):
                return None
            v = float(a[y, x])
            return v if -400 < v < 9000 else None
        return sample
    except Exception:
        return None


def analyze(lat, lng):
    """One course in -> {'feats': [['B', [[lat,lon],...]], ...],
    'green_scorer': fn([lat,lon]) -> 0..1} or None on any failure."""
    try:
        import numpy as np
        nir, red, bbox = _fetch(lat, lng)
    except Exception:
        return None
    try:
        H, W = nir.shape
        nd = (nir - red) / (nir + red + 1e-6)
        # sanity: blank / broken / off-coverage chips have no texture story
        if float(nd.std()) < 0.02:
            return None
        mpx_x = (bbox[2] - bbox[0]) * 111320.0 * math.cos(math.radians(lat)) / W
        mpx_y = (bbox[3] - bbox[1]) * 110540.0 / H
        # ---- the ground between the holes ----
        # NAIP is flown leaf-on, so irrigated turf reads as strong, smooth
        # NDVI and everything else tells you what kind of course this is:
        # trees and rough on a parkland site, decomposed granite on a desert
        # one. Measured, not guessed from the market.
        hh, ww = (H // GT) * GT, (W // GT) * GT
        ndb = nd[:hh, :ww].reshape(hh // GT, GT, ww // GT, GT).mean(axis=(1, 3))
        rdb = red[:hh, :ww].reshape(hh // GT, GT, ww // GT, GT).mean(axis=(1, 3))
        turf_m = ndb > 0.32
        bare_m = (ndb < 0.16) & (rdb > 95.0)
        off = int(turf_m.size - turf_m.sum())
        arid = round(float(bare_m.sum()) / max(1, off), 3)
        tys, txs = np.nonzero(turf_m)
        turf = [[round(bbox[3] - (int(y) * GT + GT / 2) / H * (bbox[3] - bbox[1]), 6),
                 round(bbox[0] + (int(x) * GT + GT / 2) / W * (bbox[2] - bbox[0]), 6)]
                for y, x in zip(tys.tolist(), txs.tolist())]
        turf_r = round(GT * mpx_x * 0.62 * 1.0936, 1)      # yards, disc radius
        # ---- sand: bright and not vegetated ----
        m = (nd[::G, ::G] < 0.20) & (red[::G, ::G] > 110.0)
        # On a desert course most of the chip is bright and unvegetated, so
        # blob-finding sand there is meaningless. That used to abort the whole
        # stage and hand desert courses NO imagery at all; now it only turns
        # off sand detection, and the turf mask and green votes still ship.
        sand_ok = float(m.mean()) <= 0.15
        cell = (mpx_x * G) * (mpx_y * G)
        feats = []
        for cells in (_blobs(m) if sand_ok else []):
            m2 = len(cells) * cell
            if not 25 <= m2 <= 2000:
                continue
            ys = [c[0] for c in cells]
            xs = [c[1] for c in cells]
            wg = max(xs) - min(xs) + 1
            hg = max(ys) - min(ys) + 1
            if max(wg, hg) / max(1, min(wg, hg)) > 6:
                continue                 # cart paths and roads are ribbons
            hull = _hull([(x, y) for y, x in cells[:1200]])
            poly = [[round(bbox[3] - (y * G + G / 2) / H * (bbox[3] - bbox[1]), 6),
                     round(bbox[0] + (x * G + G / 2) / W * (bbox[2] - bbox[0]), 6)]
                    for x, y in hull]
            if len(poly) >= 3:
                feats.append(['B', poly])
        # ---- turf scorer: is this spot plausibly a green? ----
        def green_scorer(pt):
            la, lo = pt[0], pt[1]
            x = int((lo - bbox[0]) / (bbox[2] - bbox[0]) * W)
            y = int((bbox[3] - la) / (bbox[3] - bbox[1]) * H)
            r = 6
            if not (r <= x < W - r and r <= y < H - r):
                return 0.5               # off-chip: neutral, never a veto
            win = nd[y - r:y + r + 1, x - r:x + r + 1]
            mu, va = float(win.mean()), float(win.var())
            s = 0.0
            if 0.18 < mu < 0.50:
                s += 0.6                 # healthy-turf reflectance band
            if va < 0.004:
                s += 0.4                 # mown-smooth texture
            return s
        return {'feats': feats, 'green_scorer': green_scorer,
                'turf': turf, 'turf_r': turf_r, 'arid': arid,
                'sand_ok': sand_ok}
    except Exception:
        return None
