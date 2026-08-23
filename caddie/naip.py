#!/usr/bin/env python3
"""NAIP imagery stage for the Caddie sweep (stage 2.5).

Pulls one USDA NAIP aerial chip per course from the USGS ImageServer
(public-domain imagery, no key required) and mines it for what
OpenStreetMap is missing:

  SAND  'B' features — bunker candidates detected as bright, low-NDVI
        blobs. generate.py only uses them on holes that have a green but
        no surveyed sand (OSM always wins) and flags the pack naip_sand,
        so the render and the app can say where the data came from.
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


def elevation_sampler(lat, lng):
    """One USGS 3DEP DEM chip per course (public domain, same family as
    NAIP). Returns fn([lat,lon]) -> elevation in meters, or None on any
    failure. Feeds facts.elev_ft: uphill/downhill per hole — the number
    behind every competitor's paywalled 'plays-like' distances."""
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
        # ---- sand: bright and not vegetated ----
        m = (nd[::G, ::G] < 0.20) & (red[::G, ::G] > 110.0)
        if float(m.mean()) > 0.15:      # deserts of "sand" = wrong imagery
            return None
        mpx_x = (bbox[2] - bbox[0]) * 111320.0 * math.cos(math.radians(lat)) / W
        mpx_y = (bbox[3] - bbox[1]) * 110540.0 / H
        cell = (mpx_x * G) * (mpx_y * G)
        feats = []
        for cells in _blobs(m):
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
        return {'feats': feats, 'green_scorer': green_scorer}
    except Exception:
        return None
