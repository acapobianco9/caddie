#!/usr/bin/env python3
"""What is actually missing from the courses we render nothing for?

`status = 'none'` means the sweep found no golf=hole centrelines. It does NOT
mean the course is unmapped, and the difference decides whether the synthesizer
is worth extending.

The synthesizer today can only FILL a gap: it needs at least one real hole line
to anchor on, and every candidate must have mapped neighbours either side. A
course with greens and tees but no centrelines produces nothing at all. Whether
that is worth fixing depends entirely on how many such courses exist, and
nobody has counted. Carroll Park, the case that raised the question, has 11
greens and ZERO tees — so a cold start would not have saved it either.

This counts. It writes nothing.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \\
        python caddie/survey_none.py [--limit N] [--all]

Buckets, per course:
  unmapped        no golf features at all — genuinely absent, or a bad coordinate
  has_holes       centrelines ARE there (so 'none' is stale or a matcher miss)
  greens+tees     no centrelines, but >=9 greens AND >=9 tees — SYNTHESIZABLE
  greens_only     greens but too few tees to pair — a green gives a location,
                  not a direction of play, so this is not synthesizable
  thin            some golf features, below both thresholds

Politeness is inherited from osm.py: same mirrors, same retry ladder, same
outage breaker. If Overpass goes down mid-survey the breaker trips and the run
reports what it got rather than grinding.
"""
import json, os, random, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import osm

SB = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ['SUPABASE_SERVICE_KEY']
SBH = {'apikey': KEY, 'Authorization': 'Bearer ' + KEY}
PAD = 0.020            # same box the sweep uses
SLEEP = float(os.environ.get('SURVEY_SLEEP', '1.6'))
MIN_SET = 9            # nine of each is the smallest routing worth drawing


def _sb_all(path):
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


def census(lat, lng):
    """One query, the same feature set the sweep asks for."""
    bb = f'{lat - PAD},{lng - PAD},{lat + PAD},{lng + PAD}'
    q = (f'[out:json][timeout:60];'
         f'way["golf"~"^(hole|green|tee)$"]({bb});out tags;')
    j = osm._try_overpass(q)
    n = {'hole': 0, 'green': 0, 'tee': 0}
    for e in j.get('elements', []):
        g = (e.get('tags') or {}).get('golf')
        if g in n:
            n[g] += 1
    return n


def bucket(n):
    if n['hole'] > 0:
        return 'has_holes'
    if n['green'] == 0 and n['tee'] == 0:
        return 'unmapped'
    if n['green'] >= MIN_SET and n['tee'] >= MIN_SET:
        return 'greens+tees'
    if n['green'] >= MIN_SET:
        return 'greens_only'
    return 'thin'


def main():
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    elif '--all' not in sys.argv:
        limit = 200

    cov = _sb_all('course_coverage?select=course_key&status=eq.none')
    keys = sorted(r['course_key'] for r in cov)
    print(f'{len(keys)} courses currently render nothing', flush=True)

    # A deterministic spread beats the first N alphabetically, which would be
    # one import batch in one metro and tell us nothing about the catalog.
    if limit and limit < len(keys):
        random.Random(20260826).shuffle(keys)
        keys = sorted(keys[:limit])
        print(f'surveying a deterministic sample of {len(keys)}', flush=True)

    courses = {}
    for i in range(0, len(keys), 100):
        chunk = ','.join(f'"{k}"' for k in keys[i:i + 100])
        for r in _sb_all(f'courses?select=key,name,info&key=in.({chunk})'):
            courses[r['key']] = r

    tally = {'unmapped': 0, 'has_holes': 0, 'greens+tees': 0,
             'greens_only': 0, 'thin': 0, 'no_coordinate': 0, 'error': 0}
    winners, examples = [], {}
    for i, k in enumerate(keys, 1):
        c = courses.get(k)
        info = (c or {}).get('info') or {}
        lat, lng = info.get('lat'), info.get('lng')
        if lat is None or lng is None:
            tally['no_coordinate'] += 1
            continue
        try:
            n = census(float(lat), float(lng))
        except Exception as e:
            tally['error'] += 1
            print(f'[{i}/{len(keys)}] {k}: ERROR {type(e).__name__}', file=sys.stderr, flush=True)
            time.sleep(SLEEP)
            continue
        b = bucket(n)
        tally[b] += 1
        examples.setdefault(b, []).append(f"{k} (h{n['hole']} g{n['green']} t{n['tee']})")
        if b == 'greens+tees':
            winners.append((k, (c or {}).get('name', ''), n['green'], n['tee']))
        print(f"[{i}/{len(keys)}] {k}: {b}  holes={n['hole']} greens={n['green']} tees={n['tee']}",
              flush=True)
        time.sleep(20.0 if osm.degraded() else SLEEP)

    done = sum(tally.values())
    print('\n' + '=' * 62)
    print(f'surveyed {done} of {len(keys)}')
    for b, v in sorted(tally.items(), key=lambda kv: -kv[1]):
        pct = (100.0 * v / done) if done else 0.0
        print(f'  {b:<14} {v:>5}   {pct:5.1f}%')
        for ex in examples.get(b, [])[:3]:
            print(f'                     e.g. {ex}')
    print('=' * 62)
    print(f'\nSYNTHESIZER ADDRESSABLE SET: {tally["greens+tees"]} of {done} '
          f'({(100.0 * tally["greens+tees"] / done) if done else 0:.1f}%)')
    print('That is the share of blank courses a cold-start synthesizer could '
          'actually draw. Anything below a few percent is not worth the risk of\n'
          'inventing a routing; a large share is a real coverage win.')
    for k, nm, g, t in winners[:25]:
        print(f'  {k}  {nm[:44]}  greens={g} tees={t}')


if __name__ == '__main__':
    main()
