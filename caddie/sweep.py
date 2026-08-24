#!/usr/bin/env python3
"""Yoink Caddie catalog sweep.

Walks the live course catalog, fetches OSM geometry per course, generates
hole packs, and upserts them into Supabase (course_holes + course_coverage).

Resumable by design: a course already marked done in course_coverage is
skipped unless --force, so the sweep can run in market-sized shards and be
re-run safely after any failure.

Environment:
    SUPABASE_URL          e.g. https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY  service-role key (repo secret; never ships to clients)

Usage:
    python caddie/sweep.py --market long_island
    python caddie/sweep.py --course phx_aguila18 --force
    python caddie/sweep.py --all --limit 200
"""
import argparse, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import osm, generate
try:
    import naip                      # stage 2.5 — needs pillow+numpy
except Exception:
    naip = None                      # OSM-only sweep still works

SUPA = os.environ.get('SUPABASE_URL', '').rstrip('/')
KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
SLEEP = float(os.environ.get('SWEEP_SLEEP', '1.6'))   # politeness between Overpass calls
BASE_MIRROR = int(os.environ.get('SWEEP_MIRROR', '0'))  # spread parallel lanes across mirrors

# pack-generator version. Bump when generate.py logic changes: a normal
# (non-force) sweep revisits any course whose coverage was written by an
# older generator, so the whole catalog upgrades itself, resumably.
# 3: NAIP stage 2.5 — imagery sand on sand-less holes + synthesizer green votes
# 4: hazard scan (penalty areas, streams, rocks, specimen trees, paths,
#    hedges, buildings) + 3DEP elevation per hole
GEN = 4


def rest(method, path, payload=None, params=''):
    url = f'{SUPA}/rest/v1/{path}{params}'
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'apikey': KEY, 'Authorization': f'Bearer {KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal'})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


# Multi-course sites where the catalog name alone can't pick the right hole
# group in OSM. Prefer info.osm_course on the courses row; this map is the
# code-side fallback. The pin is appended to the name the matcher scores.
OSM_PIN = {'bethpage': 'Black'}


def get_catalog(market=None, course=None, limit=None):
    params = '?select=key,name,market_key,info&active=eq.true'
    if market:
        params += f'&market_key=eq.{market}'
    if course:
        params += f'&key=eq.{course}'
    # PostgREST caps ANY single response at 1000 rows, whatever limit asks for,
    # so page explicitly. Without this the sweep only ever saw the first 1000
    # courses in the catalog and reported itself finished.
    rows, page = [], 0
    while True:
        batch = rest('GET', 'courses',
                     params=params + f'&order=key.asc&limit=1000&offset={page * 1000}') or []
        rows += batch
        if len(batch) < 1000 or (limit and len(rows) >= limit):
            break
        page += 1
    if limit:
        rows = rows[:limit]
    out = []
    for r in rows:
        info = r.get('info') or {}
        if info.get('lat') is None or info.get('lng') is None:
            continue
        pin = info.get('osm_course') or OSM_PIN.get(r['key'])
        nm = f"{r['name']} {pin}" if pin else r['name']
        out.append(dict(key=r['key'], name=nm, market=r['market_key'],
                        lat=float(info['lat']), lng=float(info['lng'])))
    return out


def already_done(keys):
    if not keys:
        return set()
    done = set()
    for i in range(0, len(keys), 100):
        chunk = ','.join(f'"{k}"' for k in keys[i:i+100])
        rows = rest('GET', 'course_coverage',
                    params=f'?select=course_key,status,tiers&course_key=in.({chunk})') or []
        done |= {r['course_key'] for r in rows
                 if r.get('status') in ('full', 'partial', 'none')
                 and (r.get('tiers') or {}).get('_gen') == GEN}
    return done


def upsert_course(course_key, packs, cov):
    if packs:
        rows = [{'course_key': course_key, 'hole': p['hole'], 'tier': p['tier'],
                 'par': p['par'], 'yds': p['yards']['mid'], 'pack': p} for p in packs]
        rest('POST', 'course_holes?on_conflict=course_key,hole', rows)
        # upserts never delete: when a re-sweep maps FEWER/OTHER holes (e.g.
        # bethpage re-pinned from the Green course to Black), stale rows from
        # the old set would linger and impersonate real holes. Clean them.
        keep = ','.join(str(p['hole']) for p in packs)
        try:
            rest('DELETE', 'course_holes',
                 params=f'?course_key=eq.{course_key}&hole=not.in.({keep})')
        except Exception:
            pass  # cleanup is best-effort; the upsert already landed
    rest('POST', 'course_coverage?on_conflict=course_key', [{
        'course_key': course_key, 'holes': cov['holes'],
        'tiers': {**cov['tiers'], '_gen': GEN},
        'par': cov['par'], 'yds': cov['yds'], 'status': cov['status']}])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--market')
    ap.add_argument('--course')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--shard', help='i/N — process only courses whose key hashes to lane i of N')
    ap.add_argument('--dry', action='store_true', help='no Supabase writes; print coverage')
    args = ap.parse_args()
    if not (args.market or args.course or args.all):
        ap.error('pick --market, --course, or --all')
    if not (SUPA and KEY) and not args.dry:
        ap.error('SUPABASE_URL / SUPABASE_SERVICE_KEY missing')

    cat = get_catalog(args.market, args.course, args.limit)
    print(f'catalog: {len(cat)} course(s)')
    if args.shard:
        i, n = (int(x) for x in args.shard.split('/'))
        cat = [c for c in cat if sum(ord(ch) for ch in c['key']) % n == i]
        print(f'shard {i}/{n}: {len(cat)} course(s)')
    skip = set() if (args.force or args.dry) else already_done([c['key'] for c in cat])
    if skip:
        print(f'skipping {len(skip)} already swept')

    stats = {'full': 0, 'partial': 0, 'none': 0, 'error': 0}
    for i, c in enumerate(cat):
        if c['key'] in skip:
            continue
        for attempt in range(3):
            try:
                data = osm.fetch_course(c['key'], c['name'], c['market'],
                                        c['lat'], c['lng'], mirror=BASE_MIRROR + attempt)
                # stage 2.5: one NAIP chip per course — imagery sand for
                # sand-less holes + turf votes for the synthesizer. Purely
                # best-effort: None means the course ships OSM-only.
                scorer = None
                esamp = None
                if naip is not None:
                    try:
                        n = naip.analyze(c['lat'], c['lng'])
                        if n:
                            data['f'] = data['f'] + n['feats']
                            scorer = n['green_scorer']
                    except Exception:
                        pass
                    try:
                        esamp = naip.elevation_sampler(c['lat'], c['lng'])
                    except Exception:
                        pass
                packs, cov = generate.build_course(data, green_scorer=scorer,
                                                   elev=esamp)
                if args.dry:
                    print(json.dumps(cov))
                else:
                    upsert_course(c['key'], packs, cov)
                    print(f"[{i+1}/{len(cat)}] {c['key']}: {cov['status']} "
                          f"({cov['holes']} holes, {cov['tiers']})")
                stats[cov['status']] += 1
                break
            except Exception as e:
                if attempt == 2:
                    print(f"[{i+1}/{len(cat)}] {c['key']}: ERROR {type(e).__name__}: {e}", file=sys.stderr)
                    stats['error'] += 1
                    if not args.dry:
                        try:
                            rest('POST', 'course_coverage?on_conflict=course_key',
                                 [{'course_key': c['key'], 'holes': 0, 'tiers': {},
                                   'par': 0, 'yds': 0, 'status': 'error'}])
                        except Exception:
                            pass
                else:
                    time.sleep(8 * (attempt + 1))
        time.sleep(SLEEP)
    print('sweep done:', json.dumps(stats))


if __name__ == '__main__':
    main()
