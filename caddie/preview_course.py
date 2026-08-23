#!/usr/bin/env python3
"""Render one course's stored packs into a Crown preview page.

Reads the packs straight out of Supabase (the same rows the app serves) and
writes demo/<course_key>.html. Meant to be run by the render-course workflow
so a finished course can be eyeballed without a local database.

    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python caddie/preview_course.py <course_key>
"""
import json, os, subprocess, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _get(path):
    url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + path
    key = os.environ['SUPABASE_SERVICE_KEY']
    req = urllib.request.Request(url, headers={
        'apikey': key, 'Authorization': 'Bearer ' + key, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: preview_course.py <course_key>')
    key = sys.argv[1].strip()
    q = urllib.parse.quote(key, safe='')
    rows = _get(f'course_holes?select=hole,tier,par,pack&course_key=eq.{q}&order=hole.asc')
    if not rows:
        sys.exit(f'no holes stored for {key}')
    packs = [r['pack'] for r in rows if r.get('pack')]
    course = _get(f'courses?select=name&key=eq.{q}')
    name = (course[0]['name'] if course else key)

    os.makedirs(os.path.join(ROOT, 'demo'), exist_ok=True)
    tmp = os.path.join(ROOT, 'demo', f'.{key}.packs.json')
    with open(tmp, 'w') as f:
        json.dump(packs, f)
    out = os.path.join(ROOT, 'demo', f'{key}.html')
    subprocess.run([sys.executable, os.path.join(HERE, 'crown.py'), tmp, name, out], check=True)
    os.remove(tmp)
    print(f'rendered {len(packs)} holes -> demo/{key}.html ({name})')


if __name__ == '__main__':
    main()
