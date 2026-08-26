#!/usr/bin/env python3
"""Put the card next to the ground.

Every Crown change until now has been judged against the packs -- which is
circular, because the packs are what produced the drawing. This renders each
hole's card ON TOP OF the USGS NAIP aerial of the same ground, at the same
scale and the same rotation, so a change is judged against the golf course.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python caddie/truth.py KEY [holes]

Writes demo/truth_<course_key>.html.

Georeferencing: build_hole() projects a hole into local yards about its own
tee (lat0, lon0) and rotates by ang so the hole plays up the page. GEN 10
packs carry that as pack['geo']; for older packs we re-derive it from OSM,
which is the better source anyway -- the harness should not trust the pack it
is auditing.
"""
import json, math, os, re, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import crown                                     # noqa: E402
from generate import YD_LAT, project, rot        # noqa: E402

NAIP = ('https://imagery.nationalmap.gov/arcgis/rest/services/'
        'USGSNAIPPlus/ImageServer/exportImage')
CHIP = 900          # px per side of the fetched chip
UA = 'YoinkCaddie/1.0 (truth harness; contact: anthony@amg-demolition.com)'


def _get(path):
    url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + path
    key = os.environ['SUPABASE_SERVICE_KEY']
    req = urllib.request.Request(url, headers={
        'apikey': key, 'Authorization': 'Bearer ' + key,
        'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ---------------------------------------------------------------- geometry

def card_frame(p):
    """Reproduce crown.render_hole's framing exactly: local yards -> card px."""
    line = [tuple(q) for q in p['line']]
    allp = list(line)
    if p.get('green'):
        allp += [tuple(q) for q in p['green']]
    for b in p.get('bunkers') or []:
        allp += [tuple(q) for q in b]
    allp += [tuple(q) for q in (p.get('tees') or [])]
    xs = [q[0] for q in allp]; ys = [q[1] for q in allp]
    pad = 20
    w = (max(xs) - min(xs)) or 1
    h = (max(ys) - min(ys)) or 1
    sc = min((crown.VW - 2 * pad) / w, (crown.VH - 2 * pad) / h)
    ox = (crown.VW - w * sc) / 2 - min(xs) * sc
    oy = (crown.VH - h * sc) / 2 - min(ys) * sc
    return sc, ox, oy


def local_to_ll(x, y, lat0, lon0, ang):
    """Undo the card rotation and the local projection."""
    X, Y = rot([(x, y)], -ang)[0]
    lat = lat0 - Y / YD_LAT
    lon = lon0 + X / (math.cos(math.radians(lat0)) * YD_LAT)
    return lat, lon


def chip_for_hole(p, geo):
    """A north-up NAIP bbox that covers the whole card, plus the affine
    matrix that lays that image over the card's viewBox."""
    lat0, lon0, ang = geo['lat'], geo['lon'], geo['ang']
    sc, ox, oy = card_frame(p)
    # the card's four corners, in local yards
    corners_px = [(0, 0), (crown.VW, 0), (crown.VW, crown.VH), (0, crown.VH)]
    corners_yd = [((cx - ox) / sc, (cy - oy) / sc) for cx, cy in corners_px]
    lls = [local_to_ll(x, y, lat0, lon0, ang) for x, y in corners_yd]
    lats = [q[0] for q in lls]; lons = [q[1] for q in lls]
    # a touch of margin so the rotated image never leaves a bald corner
    mlat = (max(lats) - min(lats)) * 0.06
    mlon = (max(lons) - min(lons)) * 0.06
    bb = (min(lons) - mlon, min(lats) - mlat, max(lons) + mlon, max(lats) + mlat)
    # keep the chip square in GROUND terms so NAIP does not stretch it
    W = CHIP
    H = max(1, int(round(CHIP * (bb[3] - bb[1]) * YD_LAT
                         / ((bb[2] - bb[0]) * math.cos(math.radians(lat0)) * YD_LAT))))
    url = (f'{NAIP}?bbox={bb[0]:.7f},{bb[1]:.7f},{bb[2]:.7f},{bb[3]:.7f}'
           f'&bboxSR=4326&imageSR=4326&size={W},{H}&format=jpg&f=image')

    # image px -> card px is affine; solve it from three corners
    def img_to_card(px, py):
        lon = bb[0] + px / W * (bb[2] - bb[0])
        lat = bb[3] - py / H * (bb[3] - bb[1])
        X, Y = project([(lat, lon)], lat0, lon0)[0]
        x, y = rot([(X, Y)], ang)[0]
        return x * sc + ox, y * sc + oy

    o = img_to_card(0, 0)
    ux = img_to_card(1, 0)
    uy = img_to_card(0, 1)
    a, b = ux[0] - o[0], ux[1] - o[1]
    c, d = uy[0] - o[0], uy[1] - o[1]
    return url, W, H, (a, b, c, d, o[0], o[1])


# ---------------------------------------------------------------- geo source

def geo_from_pack(p):
    g = p.get('geo')
    if isinstance(g, dict) and 'lat' in g and 'lon' in g and 'ang' in g:
        return {'lat': g['lat'], 'lon': g['lon'], 'ang': g['ang']}
    return None


def geo_from_osm(course, packs):
    """Re-derive (lat0, lon0, ang) per hole straight from the survey."""
    import osm
    info = course.get('info') or {}
    feats = osm.fetch_course(course['key'], course.get('name') or '',
                             course.get('market_key') or '',
                             info.get('lat'), info.get('lng'))
    holes = (feats or {}).get('h') or []      # fetch_course returns 'h'
    good = []
    for h in holes:
        ll = h.get('l') or []
        if len(ll) < 2:
            continue
        lat0, lon0 = ll[0]
        ln = project(ll, lat0, lon0)
        ang = -math.atan2(ln[-1][0] - ln[0][0], -(ln[-1][1] - ln[0][1]))
        # the hole number lives in 'r' (ref); 'n' is the NAME, which on a
        # multi-course property reads "Black 1", not "1"
        m = re.search(r'(\d{1,2})\s*$', str(h.get('r') or h.get('n') or ''))
        good.append((int(m.group(1)) if m else 0,
                     {'lat': lat0, 'lon': lon0, 'ang': ang}))
    out = {}
    for num, g in good:
        if num:
            out.setdefault(num, g)
    # no usable refs: fall back to survey order, which is how the packs were
    # numbered in the first place
    if not out and good:
        for i, (_, g) in enumerate(good, 1):
            out[i] = g
    print(f'osm georeference: {len(out)} of {len(holes)} holes', flush=True)
    return out, (feats or {}).get('f') or []


# ---------------------------------------------------------------- timber

def _seg_min(q, line):
    best = 1e18
    for i in range(len(line) - 1):
        ax, ay = line[i]; bx, by = line[i + 1]
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L))
        best = min(best, math.hypot(q[0] - (ax + t * dx), q[1] - (ay + t * dy)))
    return best


def timber_report(packs, geo_map, raw):
    """How far off the playing line is the nearest MAPPED timber?

    generate.PROBES stops at 55 yards. If the timber on these courses sits at
    70 or 90, extending the ladder is a one-constant fix. If there is nothing
    within 250, the woodland is simply not surveyed here and no probe ladder
    will ever find it -- which would mean the answer is imagery, not OSM.
    """
    KINDS = {'x': 'wood', 'X': 'tree_row', 'T': 'tree'}
    have = [(t, g) for t, g in raw if t in KINDS]
    rows = []
    print(f'--- timber: {len(have)} mapped features on this course ---', flush=True)
    print('hole   nearest   kind        within 55   within 100   within 200', flush=True)
    for p in packs:
        g = geo_map.get(p['hole'])
        if not g:
            continue
        line = [tuple(q) for q in p['line']]
        best, kind = 1e18, '-'
        n55 = n100 = n200 = 0
        for t, g_ll in have:
            pts = rot(project(g_ll, g['lat'], g['lon']), g['ang'])
            d = min((_seg_min(q, line) for q in pts), default=1e18)
            if d < best:
                best, kind = d, KINDS[t]
            if d <= 55: n55 += 1
            if d <= 100: n100 += 1
            if d <= 200: n200 += 1
        shown = '  none' if best > 1e17 else f'{best:6.0f}'
        print(f'{p["hole"]:>4}  {shown}   {kind:<10}  {n55:>9}   {n100:>10}   {n200:>10}',
              flush=True)
        rows.append({'hole': p['hole'], 'near': None if best > 1e17 else round(best),
                     'kind': kind, 'n55': n55, 'n100': n100, 'n200': n200})
    return rows


# ---------------------------------------------------------------- page

ART = re.compile(r'(<svg class="holeart".*?</svg>)', re.S)


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: truth.py <course_key> [hole,hole,...]')
    key = sys.argv[1].strip()
    only = set()
    if len(sys.argv) > 2 and sys.argv[2].strip():
        only = {int(x) for x in sys.argv[2].split(',') if x.strip()}

    q = urllib.parse.quote(key, safe='')
    rows = _get(f'course_holes?select=hole,par,yds,pack&course_key=eq.{q}&order=hole.asc')
    if not rows:
        sys.exit(f'no holes stored for {key}')
    course = (_get(f'courses?select=key,name,info,market_key&key=eq.{q}') or [{}])[0]
    name = course.get('name') or key
    market = course.get('market_key') or ''

    packs = [r['pack'] for r in rows if r.get('pack')]
    if only:
        packs = [p for p in packs if p['hole'] in only]
    if not packs:
        sys.exit('no holes selected')

    fallback = None
    raw = []
    cards = []
    for p in packs:
        geo = geo_from_pack(p)
        if geo is None:
            if fallback is None:
                print('pack has no geo -- re-deriving from OSM', flush=True)
                fallback, raw = geo_from_osm(course, packs)
            geo = fallback.get(p['hole'])
        if geo is None:
            print(f'[skip] hole {p["hole"]}: no georeference', flush=True)
            continue
        url, W, H, M = chip_for_hole(p, geo)
        html = crown.render_hole(p, name, market)
        m = ART.search(html)
        if not m:
            continue
        cards.append({'hole': p['hole'], 'par': p['par'], 'yds': p['yards']['mid'],
                      'art': m.group(1), 'img': url, 'w': W, 'h': H, 'm': M})

    timber = timber_report(packs, fallback or {}, raw) if raw else []

    body = []
    for c in cards:
        a, b, cc, d, e, f = c['m']
        mat = f'matrix({a:.6f},{b:.6f},{cc:.6f},{d:.6f},{e:.3f},{f:.3f})'
        body.append(f'''<section class="hole">
  <h2><b>{c['hole']}</b> par {c['par']} &middot; {c['yds']} yds</h2>
  <div class="pair">
    <figure><figcaption>Ground</figcaption>
      <div class="stage"><img src="{c['img']}" width="{c['w']}" height="{c['h']}"
           style="transform:{mat}" alt="NAIP aerial, hole {c['hole']}"></div></figure>
    <figure><figcaption>Card</figcaption>
      <div class="stage card">{c['art']}</div></figure>
    <figure><figcaption>Overlay <input type="range" min="0" max="100" value="55"
           class="sl" data-h="{c['hole']}"></figcaption>
      <div class="stage" id="ov{c['hole']}">
        <img src="{c['img']}" width="{c['w']}" height="{c['h']}" style="transform:{mat}" alt="">
        <div class="lay" style="opacity:.55">{c['art']}</div></div></figure>
  </div>
</section>''')

    if timber:
        trs = ''.join(
            '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'
            .format(t['hole'], 'none' if t['near'] is None else t['near'],
                    t['kind'], t['n55'], t['n100'], t['n200'])
            for t in timber)
        tim_html = ('<section class=timber><h2>Mapped timber</h2>'
                    '<p>Distance from the playing line to the nearest surveyed wood, '
                    'tree row or tree, and how many such features fall within each '
                    'band. generate.PROBES only looks out to 55 yards.</p>'
                    '<table><thead><tr><th>Hole</th><th>Nearest (yd)</th><th>Kind</th>'
                    '<th>within 55</th><th>within 100</th><th>within 200</th></tr>'
                    '</thead><tbody>' + trs + '</tbody></table></section>')
    else:
        tim_html = ''

    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ground truth &mdash; {name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Archivo:wght@400;600&display=swap" rel="stylesheet">
<style>{crown.CSS}
body{{background:#F2F1EC;font-family:Archivo,system-ui,sans-serif;margin:0}}
.wrap{{max-width:1180px;margin:0 auto;padding:40px 20px 80px}}
h1{{font-family:Fraunces,Georgia,serif;font-size:38px;margin:0 0 6px;letter-spacing:-.015em}}
.dek{{color:#6D7770;margin:0 0 34px;max-width:70ch;font-size:15px}}
.hole{{margin:0 0 40px}}
.hole h2{{font-family:Archivo;font-size:12px;letter-spacing:.14em;text-transform:uppercase;
 color:#6D7770;font-weight:600;margin:0 0 10px}}
.hole h2 b{{color:#14432A;font-size:15px}}
.pair{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
figure{{margin:0}}
figcaption{{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:#6D7770;
 margin:0 0 6px;display:flex;align-items:center;gap:10px;font-weight:600}}
.stage{{position:relative;width:100%;aspect-ratio:{crown.VW}/{crown.VH};overflow:hidden;
 background:#0C1710;border:1px solid #E3E3DC;border-radius:3px}}
.stage img{{position:absolute;left:0;top:0;transform-origin:0 0;image-rendering:auto}}
.stage svg{{position:absolute;left:0;top:0;width:100%;height:100%}}
.stage.card{{background:var(--card-2)}}
.lay{{position:absolute;inset:0;mix-blend-mode:normal}}
.lay svg{{background:transparent!important}}
.sl{{width:90px;accent-color:#14432A}}
.timber{{margin:44px 0 0;border-top:1px solid #E3E3DC;padding-top:22px}}
.timber h2{{font-family:Fraunces,Georgia,serif;font-size:22px;margin:0 0 6px}}
.timber p{{color:#6D7770;font-size:14px;margin:0 0 14px;max-width:70ch}}
.timber table{{border-collapse:collapse;font-size:13.5px;background:#fff;
 border:1px solid #E3E3DC;border-radius:3px}}
.timber th,.timber td{{padding:7px 14px;border-bottom:1px solid #EEEEE8;text-align:left}}
.timber th{{font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:#6D7770}}
.timber td:nth-child(n+2){{text-align:right;font-variant-numeric:tabular-nums}}
.timber td:nth-child(3){{text-align:left}}
@media(max-width:860px){{.pair{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Ground truth &mdash; {name}</h1>
<p class="dek">Each card laid over the USGS NAIP aerial of the same ground, at the
same scale and rotation. The aerial is the survey no one edited. If a bunker,
a pond or a treeline on the card does not sit on the thing in the photograph,
the generator is wrong &mdash; not the photograph.</p>
{''.join(body)}
{tim_html}
</div>
<script>
document.querySelectorAll('.sl').forEach(function(s){{
  s.addEventListener('input', function(){{
    var l = document.getElementById('ov'+s.dataset.h).querySelector('.lay');
    l.style.opacity = (s.value/100);
  }});
}});
</script></body></html>'''

    if not cards:
        sys.exit('no holes could be georeferenced -- nothing to compare')

    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    out = os.path.join(ROOT, 'demo', f'truth_{key}.html')
    open(out, 'w').write(html)
    print(f'wrote demo/truth_{key}.html ({len(cards)} holes)')


if __name__ == '__main__':
    main()
