#!/usr/bin/env python3
"""NCRDB tee sync — real tee names, par, rating and slope for every course.

Looks each covered course up in the USGA National Course Rating Database
(public lookup, facts only), parses the tee table, and upserts course_tees.
Yardages per tee are NOT here by design: the modern NCRDB publishes ratings,
not yardages — per-tee distances come from our own pack geometry, and these
rows give the tees their true names and slope.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python caddie/ncrdb.py [course_key|--all]

Polite by construction: one search + one tee page per course, 1.5 s apart,
and a course is skipped if its rows are younger than REFRESH_DAYS.
"""
import http.cookiejar, json, os, re, sys, time, urllib.parse, urllib.request

SB = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ['SUPABASE_SERVICE_KEY']
SBH = {'apikey': KEY, 'Authorization': 'Bearer ' + KEY,
       'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates'}
NCR = 'https://ncrdb.usga.org'
UA = 'YoinkCaddie/1.0 (course tee names; contact: anthony@amg-demolition.com)'
REFRESH_DAYS = 180

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_token = None


def _boot():
    """GET the search page once: antiforgery cookie + token."""
    global _token
    req = urllib.request.Request(NCR + '/', headers={'User-Agent': UA})
    html = _opener.open(req, timeout=30).read().decode('utf-8', 'replace')
    m = re.search(r'__RequestVerificationToken[^>]*value="([^"]+)"', html)
    _token = m and m.group(1)


def search(name):
    if _token is None:
        _boot()
    body = urllib.parse.urlencode({'clubName': name, 'clubCity': '',
                                   'clubState': '(Select)', 'clubCountry': 'USA'})
    req = urllib.request.Request(
        NCR + '/NCRListing?handler=LoadCourses', data=body.encode(),
        headers={'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest',
                 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                 'RequestVerificationToken': _token or ''})
    return json.loads(_opener.open(req, timeout=30).read().decode())


def tees(course_id):
    req = urllib.request.Request(f'{NCR}/courseTeeInfo?CourseID={course_id}',
                                 headers={'User-Agent': UA})
    html = _opener.open(req, timeout=30).read().decode('utf-8', 'replace')
    tbl = next((t for t in re.findall(r'<table[\s\S]*?</table>', html)
                if 'Tee Name' in t), '')
    out = []
    for tr in re.findall(r'<tr[\s\S]*?</tr>', tbl)[1:]:
        cells = [re.sub(r'<[^>]+>', '', c).strip()
                 for c in re.findall(r'<t[dh][\s\S]*?</t[dh]>', tr)]
        cells = [c for c in cells if c != '']
        if len(cells) < 6:
            continue
        name, gender, par, rating, _bogey, slope = cells[:6]
        try:
            out.append({'tee_name': name, 'gender': gender, 'par': int(par),
                        'rating': float(rating), 'slope': int(slope)})
        except ValueError:
            continue
    return out


def _norm(s):
    s = re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower())
    drop = {'golf', 'course', 'club', 'links', 'the', 'at', 'cc', 'gc', 'park',
            'state', 'country'}
    return {w for w in s.split() if w and w not in drop}


def match(course_name, cands):
    """Best NCRDB candidate by token overlap; None below the bar."""
    want = _norm(course_name)
    best, score = None, 0.0
    for c in cands:
        have = _norm(c.get('courseName', '')) | _norm(c.get('facilityName', ''))
        if not want or not have:
            continue
        s = len(want & have) / len(want | have)
        if s > score:
            best, score = c, s
    return best if score >= 0.4 else None


def _sb(method, path, payload=None):
    req = urllib.request.Request(SB + '/rest/v1/' + path, method=method,
                                 headers=SBH,
                                 data=json.dumps(payload).encode() if payload else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def sync_course(key, name):
    # freshness check
    q = urllib.parse.quote
    fresh = json.loads(_sb('GET', f'course_tees?select=updated_at&course_key=eq.{q(key)}'
                                  f'&updated_at=gte.now()-interval%27{REFRESH_DAYS}%20days%27&limit=1'))
    if fresh:
        return 'fresh'
    cands = search(name)
    time.sleep(1.5)
    hit = match(name, cands)
    if not hit:
        return 'nomatch'
    rows = tees(hit['courseID'])
    time.sleep(1.5)
    if not rows:
        return 'notees'
    for r in rows:
        r.update({'course_key': key, 'ncrdb_course_id': hit['courseID'],
                  'updated_at': 'now()'})
    _sb('POST', 'course_tees?on_conflict=course_key,tee_name,gender', rows)
    return f'{len(rows)} tees'


def _sb_all(path):
    """Read every row, not the first thousand.

    PostgREST caps ANY single response at 1000 rows whatever limit asks for.
    The sweep learned this the hard way on 24 Aug 2026: an unpaged read saw
    the first 1000 courses of 4,975 and reported itself finished. Here it
    would have been worse than a short run — the name lookup below feeds the
    NCRDB search, so an unpaged read would have searched for course KEYS
    instead of names on four courses out of five and silently found nothing.
    """
    out, page = [], 0
    while True:
        sep = '&' if '?' in path else '?'
        batch = json.loads(_sb('GET', f'{path}{sep}limit=1000&offset={page * 1000}'))
        out += batch
        if len(batch) < 1000:
            return out
        page += 1


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else '--all'
    if arg == '--all':
        courses = _sb_all('course_coverage?select=course_key'
                          '&status=in.(full,partial)&order=course_key.asc')
        keys = [c['course_key'] for c in courses]
    else:
        keys = [arg]
    names = {c['key']: c['name'] for c in _sb_all('courses?select=key,name&order=key.asc')}
    ok = miss = 0
    for k in keys:
        try:
            res = sync_course(k, names.get(k, k))
            if res in ('nomatch', 'notees'):
                miss += 1
            else:
                ok += 1
            print(f'{k}: {res}', flush=True)
        except Exception as e:
            miss += 1
            print(f'{k}: ERROR {e}', flush=True)
            time.sleep(5)
    print(f'done: {ok} synced/fresh, {miss} unmatched')


if __name__ == '__main__':
    main()
