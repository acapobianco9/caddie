#!/usr/bin/env python3
"""Render every covered course into _site/ for GitHub Pages.

One page per course (demo pages in the Crown spec) plus an index. Run by the
render-site workflow after sweeps so the sweep board's Preview buttons always
have something to open. Reads straight from Supabase.
"""
import collections, json, os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, '_site')


def _get_all(path):
    url0 = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + path
    key = os.environ['SUPABASE_SERVICE_KEY']
    out, frm = [], 0
    while True:
        req = urllib.request.Request(url0, headers={
            'apikey': key, 'Authorization': 'Bearer ' + key,
            'Range': f'{frm}-{frm + 999}'})
        with urllib.request.urlopen(req, timeout=120) as r:
            batch = json.loads(r.read().decode())
        out += batch
        if len(batch) < 1000:
            return out
        frm += 1000


def main():
    cov = _get_all('course_coverage?select=course_key,status'
                   '&status=in.(full,partial)&order=course_key.asc')
    cs = _get_all('courses?select=key,name,market_key&order=key.asc')
    names = {c['key']: c.get('name') or c['key'] for c in cs}
    # the market decides the local tree vocabulary (see crown.PALM_MARKETS)
    mkts = {c['key']: c.get('market_key') or '' for c in cs}
    rows = _get_all('course_holes?select=course_key,hole,pack'
                    '&order=course_key.asc,hole.asc')
    packs = collections.defaultdict(list)
    for r in rows:
        if r.get('pack'):
            packs[r['course_key']].append(r['pack'])

    os.makedirs(os.path.join(SITE, 'demo'), exist_ok=True)
    done, skipped = 0, 0
    items = []
    for c in cov:
        k = c['course_key']
        ps = packs.get(k)
        if not ps:
            skipped += 1
            continue
        tmp = os.path.join(SITE, f'.{k}.json')
        with open(tmp, 'w') as f:
            json.dump(ps, f)
        out = os.path.join(SITE, 'demo', f'{k}.html')
        subprocess.run([sys.executable, os.path.join(HERE, 'crown.py'),
                        tmp, names.get(k, k), out, mkts.get(k, '')], check=True,
                       stdout=subprocess.DEVNULL)
        os.remove(tmp)
        items.append((names.get(k, k), k, len(ps), c['status']))
        done += 1

    items.sort()
    lis = '\n'.join(
        f'<li><a href="demo/{k}.html">{n}</a>'
        f'<span>{h} holes &middot; {s}</span></li>'
        for n, k, h, s in items)
    page = ('<!doctype html><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex">'
            '<title>Yoink Caddie &mdash; Rendered Courses</title>'
            '<style>body{font-family:Archivo,system-ui,sans-serif;background:#F2F1EC;'
            'color:#0C1710;max-width:720px;margin:0 auto;padding:32px 20px}'
            'h1{font-family:Georgia,serif}li{list-style:none;padding:7px 0;'
            'border-bottom:1px solid #E3E3DC;display:flex;justify-content:space-between}'
            'a{color:#14432A;font-weight:600;text-decoration:none}'
            'span{color:#6D7770;font-size:13px}ul{padding:0}'
            '.style{display:flex;gap:8px;align-items:center;margin:14px 0 4px}'
            '.style b{font-size:10px;letter-spacing:.14em;color:#6D7770}'
            '.style button{font:700 12px Archivo,sans-serif;border:1.5px solid #E3E3DC;'
            'background:#fff;color:#0C1710;border-radius:999px;padding:6px 14px;cursor:pointer}'
            '.style button.on{background:#14432A;border-color:#14432A;color:#F2F6EE}'
            '#q{width:100%;margin:10px 0 4px;padding:9px 12px;font:inherit;'
            'border:1.5px solid #E3E3DC;border-radius:10px;background:#fff}</style>'
            '<h1>Rendered courses</h1><p>__DONE__ courses, live from the packs. '
            'Pick a style once &mdash; every preview opens in it.</p>'
            '<div class="style"><b>STYLE</b>'
            '<button data-s="book">The Book</button>'
            '<button data-s="crown">Gen 11</button></div>'
            '<input id="q" placeholder="Filter courses or markets&hellip;">'
            '<ul>__LIS__</ul>'
            '<script>'
            'var cur="book";try{cur=localStorage.getItem("caddie-style")||"book"}catch(e){}'
            'function setS(s){cur=s;try{localStorage.setItem("caddie-style",s)}catch(e){}'
            'document.querySelectorAll(".style button").forEach(function(b){b.classList.toggle("on",b.dataset.s===s)});'
            'document.querySelectorAll("ul a").forEach(function(a){a.href=a.href.split("#")[0]+"#style="+s});}'
            'document.querySelectorAll(".style button").forEach(function(b){b.onclick=function(){setS(b.dataset.s)}});'
            'setS(cur==="crown"?"crown":"book");'
            'var q=document.getElementById("q");'
            'q.oninput=function(){var v=q.value.trim().toLowerCase();'
            'document.querySelectorAll("ul li").forEach(function(li){'
            'li.style.display=!v||li.textContent.toLowerCase().indexOf(v)>-1?"":"none"});};'
            '</scr'+'ipt>').replace('__DONE__', str(done)).replace('__LIS__', lis)
    with open(os.path.join(SITE, 'index.html'), 'w') as f:
        f.write(page)
    print(f'rendered {done} courses ({skipped} covered-but-empty skipped)')


if __name__ == '__main__':
    main()
