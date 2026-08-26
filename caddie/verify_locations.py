#!/usr/bin/env python3
"""Is each course where we say it is?

Weathervane Golf Club is in Weymouth, Massachusetts. We had it at 40.68,
-73.392 — Massapequa, Long Island — filed under the long_island market. The
town and the name were right; the coordinate and the market were both wrong,
and the coordinate agreed with the market rather than the course.

That coordinate is what the sweep hands to Overpass, so a wrong one is not a
cosmetic problem. Weathervane happened to land on open ground and swept to
zero holes. A wrong coordinate that lands NEAR ANOTHER GOLF COURSE produces a
full set of real holes filed under the wrong club, and nothing about that
looks broken from the outside. This script exists to find those.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \\
        python caddie/verify_locations.py [--all | --batch NAME | --market KEY]

Geocoder is Nominatim, one request per second with a contact in the
user-agent, per their usage policy. ~5,100 courses is about 95 minutes.
Nothing is written: this prints a report and exits 1 if anything is flagged.
"""
import json, math, os, sys, time, urllib.parse, urllib.request

SB = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ['SUPABASE_SERVICE_KEY']
SBH = {'apikey': KEY, 'Authorization': 'Bearer ' + KEY}
NOM = 'https://nominatim.openstreetmap.org/search'
UA = 'YoinkCaddie/1.0 (course location audit; contact: anthony@amg-demolition.com)'

# A course found by NAME should sit within 40 km of where we put it.
#
# There is deliberately NO town-only fallback. A bare town name is ambiguous
# across states — "Bishop, USA" resolves to Bishop, California, not Bishop,
# Georgia; "Carthage" lands in Texas, not Missouri — and the first pass of
# this audit produced three confident false positives that way inside eleven
# courses. If the named course does not geocode, the course is UNVERIFIED,
# which is an honest answer. It is not evidence of a problem.
BAR_NAME = 40.0
PAUSE = 1.1


def _sb_all(path):
    """PostgREST caps any response at 1000 rows, so page. (Learned 24 Aug 2026.)"""
    out, page = [], 0
    while True:
        sep = '&' if '?' in path else '?'
        req = urllib.request.Request(
            f'{SB}/rest/v1/{path}{sep}limit=1000&offset={page * 1000}', headers=SBH)
        with urllib.request.urlopen(req, timeout=60) as r:
            batch = json.loads(r.read().decode())
        out += batch
        if len(batch) < 1000:
            return out
        page += 1


def haversine(a, b, c, d):
    R = 6371.0
    dl, dg = math.radians(c - a), math.radians(d - b)
    q = (math.sin(dl / 2) ** 2
         + math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(dg / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(q))


def geocode(q):
    url = NOM + '?' + urllib.parse.urlencode({'format': 'json', 'limit': 1, 'q': q})
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            hits = json.loads(r.read().decode())
    except Exception:
        return None
    return (float(hits[0]['lat']), float(hits[0]['lon'])) if hits else None


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else '--all'
    val = sys.argv[2] if len(sys.argv) > 2 else ''
    sel = 'courses?select=key,name,region,market_key,info,active&order=key.asc'
    if arg == '--batch':
        sel += f'&info->>batch=eq.{urllib.parse.quote(val)}'
    elif arg == '--market':
        sel += f'&market_key=eq.{urllib.parse.quote(val)}'
    rows = _sb_all(sel)

    flagged, unverified, checked = [], [], 0
    for r in rows:
        info = r.get('info') or {}
        lat, lng = info.get('lat'), info.get('lng')
        # Prefer the course's own town over the market region. "Herndon
        # Centennial Golf Course, Herndon, USA" resolves; the same name with
        # "State Parks" appended does not. The course NAME is still the anchor,
        # so this is not the town-only fallback the docstring rules out — it
        # only sharpens a query that already names the course.
        town = (info.get('town') or r.get('region') or '').strip()
        if lat is None or lng is None:
            unverified.append((r['key'], 'no stored coordinate'))
            continue
        hit = geocode(f"{r['name']}, {town}, USA")
        time.sleep(PAUSE)
        if not hit:
            unverified.append((r['key'], 'course name did not geocode'))
            continue
        km = haversine(lat, lng, hit[0], hit[1])
        checked += 1
        if km > BAR_NAME:
            flagged.append((r['key'], r['name'], town, r['market_key'],
                            round(km), (lat, lng), (round(hit[0], 3), round(hit[1], 3))))
            print(f'FLAG {km:6.0f} km  {r["key"]}\n'
                  f'      {r["name"]} — {town} [{r["market_key"]}]\n'
                  f'      stored {lat},{lng}   geocoded {hit[0]:.3f},{hit[1]:.3f}',
                  flush=True)

    print(f'\nchecked {checked}, flagged {len(flagged)}, unverified {len(unverified)}')
    for k, why in unverified[:40]:
        print(f'  unverified: {k} — {why}')
    if flagged:
        sys.exit(f'{len(flagged)} course(s) are not where we say they are')


if __name__ == '__main__':
    main()
