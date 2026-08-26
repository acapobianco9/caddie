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
# While the outage breaker is open the sweep is probing, not working. Walk the
# catalog slowly then, so a long Overpass outage does not race through it
# writing error rows and asking a struggling service for more.
OUTAGE_SLEEP = float(os.environ.get('SWEEP_OUTAGE_SLEEP', '20'))
BASE_MIRROR = int(os.environ.get('SWEEP_MIRROR', '0'))  # spread parallel lanes across mirrors

# pack-generator version. Bump when generate.py logic changes: a normal
# (non-force) sweep revisits any course whose coverage was written by an
# older generator, so the whole catalog upgrades itself, resumably.
# 3: NAIP stage 2.5 — imagery sand on sand-less holes + synthesizer green votes
# 4: hazard scan (penalty areas, streams, rocks, specimen trees, paths,
#    hedges, buildings) + 3DEP elevation per hole
# 5: honest trees — timber draws only where the survey has it AND it sits
#    inside the miss cone. No dogleg fallback, no automatic par-3 backdrop.
# 6: trees read properly — GEN 5 saw only wood polygons, so 44 of 230 courses
#    got a single tree. Tree rows and clusters of individual tree nodes now
#    count too. Still detection only; the miss cone still decides.
# 7: the ground. Every hole used to be drawn as parkland whatever it sat on.
#    Reads intermittent water (a dry wash is ground, not a lake), coastline,
#    sand, saltmarsh and clifftop from OSM; the irrigated turf mask and how
#    arid the ground between the holes is from NAIP; dune and bluff crests
#    from 3DEP. Three grounds ship - parkland, desert, links - and a hole
#    with no signal stays parkland, so this can only add. Also finds the
#    forward tees and measures the hole from each one.
# 8: what GEN 7's first real pass exposed. (a) A golf=penalty_area with no
#    water in it is GROUND, not water - post-2019 tagging files desert scrub
#    and native area under that key and we painted every one blue, including a
#    603-yard one at Angeles National. That, not the intermittent wash, was
#    "water world". (b) Desert no longer requires a course to have zero water,
#    so every desert course with an irrigation pond stops coming back parkland.
#    (c) A clifftop only makes a seaside hole if there is a coastline near it -
#    inland canyon walls were drawing an ocean in the foothills.
# 9: the desert stopped being a guess. `arid` is computed from absolute NDVI
#    on a chip the imagery server has already contrast-stretched, so it never
#    could tell Illinois from Arizona - measured on Aug 25 2026 its median was
#    0.609 in Chicago against 0.328 in Washington, 5,540 holes were already
#    drawn as desert, and 9,487 of the 16,014 holes carrying a reading sat
#    above the 0.45 line GEN 8 had just made sufficient on its own. Herndon
#    Centennial, Virginia, rendered six desert holes. Desert now needs the
#    survey to agree: OSM has to have found arid ground on the hole (dry wash,
#    dry channel, scrub penalty area, or sand that is not a beach) AND the
#    chip has to read bare. Also records arid_sep, a contrast-invariant
#    aridity metric, so the next pass produces data to calibrate against.
GEN = 9


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


# QUEUE ORDER. A course with no coverage row has no card at all; a course
# already rendered has one that is merely a generation behind. So untouched
# courses go first, then the ones whose fetch failed, then re-renders, and
# last the ones OSM had nothing for.
#
# It ran the other way round until Aug 26 2026, and the cost was measurable:
# 2,471 of 4,974 catalog courses had never been swept at all, and with
# rendered-first the run was adding new courses at 18/hr while doing 71/hr
# overall -- three quarters of the work went to courses that already had a
# drawing. At that rate the untouched half of the catalog was six days out.
#
# Ties break on key so lanes resume deterministically across cron relaunches.
PRIO_NEW, PRIO_ERROR, PRIO_RENDERED, PRIO_EMPTY = 0, 1, 2, 3


def coverage_state(keys):
    """(set already swept at this GEN, {course_key: sort priority})."""
    done, prio = set(), {}
    for i in range(0, len(keys), 100):
        chunk = ','.join(f'"{k}"' for k in keys[i:i+100])
        rows = rest('GET', 'course_coverage',
                    params=f'?select=course_key,status,holes,tiers'
                           f'&course_key=in.({chunk})') or []
        for r in rows:
            k, st = r['course_key'], r.get('status')
            if (st in ('full', 'partial', 'none')
                    and (r.get('tiers') or {}).get('_gen') == GEN):
                done.add(k)
            if st in ('full', 'partial'):
                prio[k] = (PRIO_RENDERED, -(r.get('holes') or 0))
            elif st == 'error':
                prio[k] = (PRIO_ERROR, 0)
            elif st == 'none':
                prio[k] = (PRIO_EMPTY, 0)
    return done, prio


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
    skip, prio = set(), {}
    if SUPA and KEY:
        done, prio = coverage_state([c['key'] for c in cat])
        if not (args.force or args.dry):
            skip = done
    cat.sort(key=lambda c: prio.get(c['key'], (PRIO_NEW, 0)) + (c['key'],))
    # courses that already have a book — a failed fetch must never overwrite one
    rendered = {k for k, v in prio.items() if v[0] == PRIO_RENDERED}
    if skip:
        print(f'skipping {len(skip)} already swept')
    if prio:
        q = [0, 0, 0, 0]
        for c in cat:
            if c['key'] not in skip:
                q[prio.get(c['key'], (PRIO_NEW, 0))[0]] += 1
        print(f'queue: {q[PRIO_RENDERED]} rendered · {q[PRIO_ERROR]} error-retry '
              f'· {q[PRIO_NEW]} new · {q[PRIO_EMPTY]} empty')

    stats = {'full': 0, 'partial': 0, 'none': 0, 'error': 0}
    for i, c in enumerate(cat):
        if c['key'] in skip:
            continue
        for attempt in range(3):
            try:
                data = osm.fetch_course(c['key'], c['name'], c['market'],
                                        c['lat'], c['lng'], mirror=BASE_MIRROR + attempt)
                # stage 2.5: one NAIP chip and one 3DEP chip per course —
                # imagery sand for sand-less holes, turf votes for the
                # synthesizer, and (GEN 7) the ground the hole sits on plus
                # dune and bluff crests. Purely best-effort: a failure here
                # means the course ships OSM-only, never that it fails.
                scorer = None
                esamp = None
                gnd = {}
                if naip is not None:
                    try:
                        n = naip.analyze(c['lat'], c['lng'])
                        if n:
                            data['f'] = data['f'] + n['feats']
                            scorer = n['green_scorer']
                            # GEN 7: the ground between the holes. `arid` says
                            # whether this is a desert course; the turf mask
                            # says where the irrigation actually reaches.
                            gnd['turf'] = n.get('turf') or []
                            gnd['turf_r'] = n.get('turf_r')
                            gnd['arid'] = n.get('arid')
                    except Exception:
                        pass
                    try:
                        esamp, ridges = naip.terrain(c['lat'], c['lng'])
                        gnd['ridges'] = ridges
                    except Exception:
                        pass
                packs, cov = generate.build_course(data, green_scorer=scorer,
                                                   elev=esamp, ground=gnd or None)
                if args.dry:
                    print(json.dumps(cov))
                else:
                    upsert_course(c['key'], packs, cov)
                    print(f"[{i+1}/{len(cat)}] {c['key']}: {cov['status']} "
                          f"({cov['holes']} holes, {cov['tiers']})")
                stats[cov['status']] += 1
                break
            except Exception as e:
                # While Overpass is down, a second and third go at the same
                # course are just two more ways to wait for the same answer.
                if attempt < 2 and not osm.degraded():
                    time.sleep(8 * (attempt + 1))
                    continue
                print(f"[{i+1}/{len(cat)}] {c['key']}: ERROR {type(e).__name__}: {e}", file=sys.stderr)
                stats['error'] += 1
                if c['key'] in rendered:
                    # This course already has a book. Writing the error row
                    # would replace its status, holes, par and yards with
                    # zeroes and strand the packs still sitting in
                    # course_holes. That is not a thought experiment: on
                    # Aug 25 2026 an Overpass outage marked 156 courses
                    # 'error' this way — Bethpage and Angeles National among
                    # them — while their 16 and 18 holes sat untouched in the
                    # table. A failed fetch is evidence about Overpass, not
                    # about the golf course.
                    print(f'[keep] {c["key"]}: fetch failed, '
                          f'previous coverage left intact', flush=True)
                elif not args.dry:
                    try:
                        rest('POST', 'course_coverage?on_conflict=course_key',
                             [{'course_key': c['key'], 'holes': 0, 'tiers': {},
                               'par': 0, 'yds': 0, 'status': 'error'}])
                    except Exception:
                        pass
                break
        time.sleep(OUTAGE_SLEEP if osm.degraded() else SLEEP)
    print('sweep done:', json.dumps(stats))


if __name__ == '__main__':
    main()
