#!/usr/bin/env python3
"""Render Caddie hole packs into the CROWN design (crowned greens hybrid).

Same contract as preview.py — consumes ONLY pack JSON — but draws the Crown
language: the green's own outline stroked wide in the deeper tone and clipped
to itself (the crown band), a cup and pin, tonal bunker faces, banded water,
mixed-hand trees and fescue, and type that never lets the handwriting touch
a number.

CANONICAL DESIGN SPEC ("Fescue Study IV", Aug 23 2026 — owner-approved).
caddie.js in the app must match this file: the three tree hands (cone /
spruce / broad, mixed 5:3:2), the three fescue hands (fan / arc / sedge,
mixed 4:3:3), the measured-density curve (tuft spacing 44-34d yd, skip
0.68-0.6d, size x(0.72+0.55d) where d = imagery coverage fraction), the
straw palette (#A2925A / #877947), and every hazard mark below (streams,
rock, hedges, cart paths, buildings, specimen trees, elevation readout).
Owner-picked hands, Aug 23 2026: rocks R1 (river-stone cluster + scree),
structures S3 (shed doodle under 30 px span, plan footprint above),
fences/walls F1 (post-and-rail); hedges stay the green stitch.

    python caddie/crown.py packs.json "Course Name" out.html
"""
import json, math, random, sys

VW, VH = 334, 430

# Structures are OFF for this iteration (owner call, Aug 23 2026). The shed
# hand and the plan-view footprint both stay in the file; flip this to True
# to bring buildings back without touching the renderer.
DRAW_STRUCTURES = False

# Fences and walls are OFF too (owner call, Aug 23 2026). The post-and-rail
# hand stays below; hedges are unaffected and keep the green stitch.
DRAW_FENCES = False


def catmull(P, closed=False):
    n = len(P)
    if n < 2: return ''
    if n == 2: return f'M{P[0][0]:.1f},{P[0][1]:.1f} L{P[1][0]:.1f},{P[1][1]:.1f}'
    def gp(i): return P[i % n] if closed else P[max(0, min(n - 1, i))]
    d = f'M{P[0][0]:.1f},{P[0][1]:.1f} '
    for i in (range(n) if closed else range(n - 1)):
        p0, p1, p2, p3 = gp(i-1), gp(i), gp(i+1), gp(i+2)
        c1 = (p1[0] + (p2[0]-p0[0])/6, p1[1] + (p2[1]-p0[1])/6)
        c2 = (p2[0] - (p3[0]-p1[0])/6, p2[1] - (p3[1]-p1[1])/6)
        d += f'C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f} '
    if closed: d += 'Z'
    return d

def scale_pts(pts, f, dy=0):
    cx = sum(p[0] for p in pts)/len(pts); cy = sum(p[1] for p in pts)/len(pts)
    return [(cx+(x-cx)*f, cy+(y-cy)*f+dy) for x, y in pts]

def arclen(line):
    return sum(math.hypot(line[i+1][0]-line[i][0], line[i+1][1]-line[i][1]) for i in range(len(line)-1))

def point_at_arc(line, arc):
    cum = 0
    for i in range(len(line)-1):
        L = math.hypot(line[i+1][0]-line[i][0], line[i+1][1]-line[i][1])
        if cum + L >= arc:
            t = (arc-cum)/L
            return (line[i][0]+t*(line[i+1][0]-line[i][0]), line[i][1]+t*(line[i+1][1]-line[i][1]))
        cum += L
    return line[-1]

def dir_at_arc(line, arc):
    cum = 0
    for i in range(len(line)-1):
        L = math.hypot(line[i+1][0]-line[i][0], line[i+1][1]-line[i][1])
        if cum + L >= arc:
            return ((line[i+1][0]-line[i][0])/L, (line[i+1][1]-line[i][1])/L)
        cum += L
    dx = line[-1][0]-line[-2][0]; dy = line[-1][1]-line[-2][1]; L = math.hypot(dx, dy) or 1
    return (dx/L, dy/L)

def pip(pt, poly):
    x, y = pt; inside = False; n = len(poly); j = n-1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj-xi)*(y-yi)/((yj-yi) or 1e-9)+xi:
            inside = not inside
        j = i
    return inside

# three tree hands: the classic two-tier conifer, a taller three-tier spruce,
# and a round broadleaf — mixed by seeded chance so no two stands read alike
CONE = "M0,-15 l7,10 h-4 l6,9 h-18 l6,-9 h-4 z"
SPRUCE = "M0,-21 l5,7 h-3 l5,7 h-3.5 l6,8 h-19 l6,-8 h-3.5 l5,-7 h-3 z"
def cone_svg(x, y, s, cls, kind='cone'):
    g = f'<g transform="translate({x:.1f},{y-11*s:.1f}) scale({s:.3f})">'
    if kind == 'spruce':
        return g + f'<path class="{cls}" d="{SPRUCE}"/><path class="trunk" d="M0,4 v7"/></g>'
    if kind == 'broad':
        return (g + f'<ellipse class="{cls}" cx="0" cy="-3" rx="7.6" ry="7"/>'
                    f'<path class="trunk" d="M0,4 v7"/></g>')
    return g + f'<path class="{cls}" d="{CONE}"/><path class="trunk" d="M0,4 v7"/></g>'

# three fescue hands: a full seven-blade fan, a sparser wind-leaned arc, and a
# low sedge clump — mixed the same way, so the long grass looks grown, not tiled
TUFTS = {
    'fan': ('M0,0 C-0.6,-3 -2.2,-6 -4.6,-8.2 M0,0 C-0.3,-3.6 -1.1,-7.2 -2.1,-9.6 '
            'M0,0 C0.2,-3.6 0.5,-7.4 0.2,-10.2 M0,0 C0.6,-3.1 1.7,-6.6 3.1,-8.8 '
            'M0,0 C1.1,-2.6 3,-5 5.1,-6.6 M-1.8,0 C-3,-1.8 -4.6,-3.2 -6.2,-4.2 '
            'M1.8,0 C3.1,-1.8 4.8,-3.1 6.4,-4.1'),
    'arc': ('M0,0 C-0.4,-3 -1.6,-6.4 -3.4,-8.8 M0,0 C0.1,-3.6 0.2,-7.4 -0.6,-10 '
            'M0,0 C0.7,-3 2.2,-6 4.4,-7.6 M0,0 C1.4,-2.2 3.4,-4 5.6,-5'),
    'sedge': ('M0,0 C-1,-2 -3,-4 -5.6,-5 M0,0 C-0.5,-2.6 -1.2,-5 -2,-6.6 '
              'M0,0 C0.3,-2.6 0.8,-5.2 0.6,-7 M0,0 C0.9,-2.4 2.2,-4.6 3.8,-5.8 '
              'M0,0 C1.4,-1.8 3.4,-3.2 5.8,-3.8'),
}
TUFT_SEEDS = {'fan': ((-2.1, -9.6), (3.1, -8.8)), 'arc': ((-0.6, -10.0),), 'sedge': ()}

# two boulder hands: rounded-angular stones with a single facet line — small
# rock features draw as a stone cluster, big scree fields keep their outline
# and grow stones inside it
BOULDERS = {
    'b1': ('M-6,2 C-7.2,-2 -4.5,-5.2 0,-5.6 C4.5,-6 7.2,-3 6.6,0.8 '
           'C6.1,3.8 2.4,5.1 -2,4.7 C-4.8,4.4 -5.4,3.6 -6,2 Z', 'M-3.4,-3.8 L0.8,-1.2 L4.8,-2.2'),
    'b2': ('M-4.4,1.4 C-5,-1.2 -3,-3.6 0.2,-3.8 C3.2,-4 5,-2 4.6,0.6 '
           'C4.2,2.6 1.6,3.6 -1.4,3.3 C-3.4,3.1 -4,2.6 -4.4,1.4 Z', 'M-2.2,-2.6 L1,-0.8'),
}
def boulder_svg(x, y, s, kind='b1'):
    body, facet = BOULDERS[kind]
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.2f})">'
            f'<path class="rock" d="{body}"/><path class="rock-l" d="{facet}"/></g>')
# the shed (owner-picked S3): mono-pitch work shed with plank doors — the
# pictorial hand for small buildings; big footprints stay quiet plan-view
def shed_svg(x, y, s):
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.2f})">'
            f'<path class="shed-b" d="M-8,0 L-8,6.5 L8,6.5 L8,0 Z"/>'
            f'<path class="shed-r" d="M-9.2,0.6 L-6,-5.5 L9.2,-1.8 L8,0 Z"/>'
            f'<path class="shed-d" d="M-2.2,6.5 L-2.2,1.2 L2.2,1.2 L2.2,6.5"/>'
            f'<line class="shed-l" x1="0" y1="1.2" x2="0" y2="6.5"/></g>')
def tuft_svg(x, y, s, cls, kind='fan'):
    seeds = ''.join(f'<circle class="{cls}-seed" cx="{sx}" cy="{sy}" r="0.9"/>'
                    for sx, sy in TUFT_SEEDS[kind])
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.2f})">'
            f'<path class="{cls}" d="{TUFTS[kind]}"/>{seeds}</g>')


def render_hole(p, course_name):
    line = [tuple(q) for q in p['line']]
    total = arclen(line)
    par = p['par']
    hid = p['hole']
    allp = list(line)
    if p['green']: allp += [tuple(q) for q in p['green']]
    for b in p['bunkers']: allp += [tuple(q) for q in b]
    allp += [tuple(q) for q in p['tees']]
    xs = [q[0] for q in allp]; ys = [q[1] for q in allp]
    pad = 20
    w, h = (max(xs)-min(xs)) or 1, (max(ys)-min(ys)) or 1
    sc = min((VW-2*pad)/w, (VH-2*pad)/h)
    ox = (VW-w*sc)/2 - min(xs)*sc; oy = (VH-h*sc)/2 - min(ys)*sc
    def PX(q): return (q[0]*sc+ox, q[1]*sc+oy)
    tee_px = PX(line[0])
    ev0 = (p.get('facts') or {}).get('elev_ft') or 0
    S = []
    # distance arcs under everything
    for ryd in ([150, 250] if par > 3 else ([100] if total > 130 else [])):
        if ryd > total-25: continue
        rr = ryd*sc
        pts = [(tee_px[0]+rr*math.sin(math.radians(a)), tee_px[1]-rr*math.cos(math.radians(a)))
               for a in range(-42, 43, 12)]
        S.append(f'<path class="arc" d="{catmull(pts)}"/>')
        S.append(f'<text class="arclab" x="{pts[0][0]-3:.0f}" y="{pts[0][1]-3:.0f}" text-anchor="end">{ryd}</text>')
    # corridor: three nested bands
    if par > 3:
        fw = max(20, min(58, 34*sc)); rw = fw*1.55; tw = min(146, fw*2.15)
        jit = random.Random(hid*5+2)
        def band(a0, a1, n=7):
            pts = [point_at_arc(line, a0+(a1-a0)*i/(n-1)) for i in range(n)]
            pts = [(x+jit.uniform(-2.5, 2.5), y) for x, y in pts]
            return catmull([PX(q) for q in pts])
        d_t = band(0, max(30, total-12)); d_r = band(0, max(28, total-16))
        for cls, dd, wd in (('tree-o', d_t, tw+1), ('tree', d_t, tw), ('rgh-o', d_r, rw+1),
                            ('rgh', d_r, rw)):
            S.append(f'<path class="{cls}" style="stroke-width:{wd:.0f}px" d="{dd}"/>')
        # short grass only where the survey says there IS short grass — a hole
        # with a forced carry off the tee shows rough until the fairway starts.
        # Real intervals get ROUND caps (a fairway ends in a nose, not a cut);
        # the endpoints are inset half the band width so the bulge of the cap
        # lands exactly on the surveyed yardage.
        if p.get('fw'):
            halfyd = (fw / sc) / 2
            for s, e in p['fw']:
                s0, e0 = max(6, s) + halfyd, min(e, total - 14) - halfyd
                if e0 - s0 < 8:
                    mid = (max(6, s) + min(e, total - 14)) / 2
                    s0 = e0 = mid
                d_f = band(s0, max(e0, s0 + 0.5), n=max(3, int((e0-s0)/70)+2))
                for cls, wd in (('fat-o', fw+1), ('fat', fw)):
                    S.append(f'<path class="{cls}" style="stroke-width:{wd:.0f}px;'
                             f'stroke-linecap:round" d="{d_f}"/>')
        else:
            # a provisional (synthetic) hole draws its assumed path dashed —
            # the drawing itself says "the line is a guess"
            dash = ';stroke-dasharray:16 11' if p.get('synthetic') else ''
            d_f = band(6, max(24, total-24))
            for cls, wd in (('fat-o', fw+1), ('fat', fw)):
                S.append(f'<path class="{cls}" style="stroke-width:{wd:.0f}px{dash}" d="{d_f}"/>')
        # dispersion cone: the honest version of "aim here"
        tgt = min(258, total-55)
        if tgt > 90 and not p.get('synthetic'):
            la, ra = [], []
            for i in range(6):
                a = 8+(tgt-8)*i/5
                q = point_at_arc(line, a); dx, dy = dir_at_arc(line, a)
                wyd = (3+(a-8)/(tgt-8)*26)
                la.append(PX((q[0]-dy*wyd, q[1]+dx*wyd)))
                ra.append(PX((q[0]+dy*wyd, q[1]-dx*wyd)))
            S.append(f'<path class="disp" d="{catmull(la)} L{" L".join(f"{x:.1f},{y:.1f}" for x, y in reversed(ra))} Z"/>')
    elif p['green']:
        gP0 = [PX(tuple(q)) for q in p['green']]
        gcx = sum(q[0] for q in gP0)/len(gP0); gcy = sum(q[1] for q in gP0)/len(gP0)
        gw = max(q[0] for q in gP0)-min(q[0] for q in gP0)
        r1 = max(96, gw*2.4); r2 = r1*0.76
        S.append(f'<ellipse cx="{gcx:.0f}" cy="{gcy:.0f}" rx="{r1:.0f}" ry="{r1*0.68:.0f}" fill="var(--turf-1)" stroke="var(--ink)" stroke-opacity=".07" stroke-width="1"/>')
        S.append(f'<ellipse cx="{gcx:.0f}" cy="{gcy:.0f}" rx="{r2:.0f}" ry="{r2*0.67:.0f}" fill="var(--turf-2)" stroke="var(--ink)" stroke-opacity=".15" stroke-width="1"/>')
    # cart paths first: they run under everything
    for pl in (p.get('paths') or []):
        P = [PX(tuple(q)) for q in pl]
        S.append(f'<path class="cpath" d="{catmull(P)}"/>')
    # structures (owner-picked S3): small buildings draw as the shed doodle;
    # big footprints keep straight plan-view edges + ridge so a clubhouse
    # never wears a tiny shed costume
    for bl in ((p.get('bldgs') or []) if DRAW_STRUCTURES else []):
        P = [PX(tuple(q)) for q in bl]
        bx0 = min(q[0] for q in P); bx1 = max(q[0] for q in P)
        by0 = min(q[1] for q in P); by1 = max(q[1] for q in P)
        bcx, bcy = (bx0+bx1)/2, (by0+by1)/2
        bspan = max(bx1-bx0, by1-by0)
        if bspan < 30:
            S.append(shed_svg(bcx, bcy, max(0.9, min(1.6, bspan/14))))
            continue
        dd = ' '.join(f'L{x:.1f},{y:.1f}' for x, y in P[1:])
        S.append(f'<path class="bldg" d="M{P[0][0]:.1f},{P[0][1]:.1f} {dd} Z"/>')
        if (bx1-bx0) >= (by1-by0):
            rx = (bx1-bx0)*0.32
            S.append(f'<line class="ridge" x1="{bcx-rx:.1f}" y1="{bcy:.1f}" x2="{bcx+rx:.1f}" y2="{bcy:.1f}"/>')
        else:
            ry = (by1-by0)*0.32
            S.append(f'<line class="ridge" x1="{bcx:.1f}" y1="{bcy-ry:.1f}" x2="{bcx:.1f}" y2="{bcy+ry:.1f}"/>')
    # streams: a creek is drawn as moving water, not a pond
    for sl in (p.get('streams') or []):
        P = [PX(tuple(q)) for q in sl]
        S.append(f'<path class="strm-o" d="{catmull(P)}"/>')
        S.append(f'<path class="strm" d="{catmull(P)}"/>')
    # water: banded edge, same mark as the crown
    for wply in p['waters']:
        P = [PX(tuple(q)) for q in wply]
        S.append(f'<path class="wat" d="{catmull(P, True)}"/>')
        S.append(f'<path class="shallow" d="{catmull(scale_pts(P, 0.82), True)}"/>')
    # rock: small features draw as a hand-drawn stone cluster; big scree
    # fields keep their surveyed outline with stones scattered inside
    rockR = random.Random(hid*13+7)
    for rply in (p.get('rocks') or []):
        P = [PX(tuple(q)) for q in rply]
        rx0 = min(q[0] for q in P); rx1 = max(q[0] for q in P)
        ry0 = min(q[1] for q in P); ry1 = max(q[1] for q in P)
        cx = sum(q[0] for q in P)/len(P); cy = sum(q[1] for q in P)/len(P)
        span = max(rx1-rx0, ry1-ry0)
        if span < 26:
            # boulder cluster: one big stone, one or two smaller companions
            S.append(boulder_svg(cx, cy, 1.0 + rockR.random()*0.4, 'b1'))
            S.append(boulder_svg(cx + 7 + rockR.random()*3, cy + 3, 0.7, 'b2'))
            if rockR.random() < 0.6:
                S.append(boulder_svg(cx - 7, cy + 4 + rockR.random()*2, 0.55, 'b2'))
        else:
            dd = ' '.join(f'L{x:.1f},{y:.1f}' for x, y in P[1:])
            S.append(f'<path class="scree" d="M{P[0][0]:.1f},{P[0][1]:.1f} {dd} Z"/>')
            for _ in range(min(6, max(3, int(span/16)))):
                sx = rx0 + rockR.random()*(rx1-rx0)
                sy = ry0 + rockR.random()*(ry1-ry0)
                if pip((sx, sy), P):
                    S.append(boulder_svg(sx, sy, 0.5 + rockR.random()*0.5,
                                         rockR.choice(['b1', 'b2'])))
    # hedges / walls: a stitched line — something you cannot fly low over
    for hl in (p.get('hedges') or []):
        P = [PX(tuple(q)) for q in hl]
        S.append(f'<path class="hedge" d="{catmull(P)}"/>')
    # fences & walls (owner-picked F1): post-and-rail — one timber rail with
    # posts stepping along the true line
    for fl in ((p.get('fences') or []) if DRAW_FENCES else []):
        P = [PX(tuple(q)) for q in fl]
        if len(P) < 2:
            continue
        S.append(f'<path class="rail" d="{catmull(P)}"/>')
        fR = random.Random(hid*29 + int(P[0][0]))
        cum = 0.0; nextat = 9.0
        for i in range(len(P)-1):
            x0, y0 = P[i]; x1, y1 = P[i+1]
            L = math.hypot(x1-x0, y1-y0)
            while L > 0 and nextat <= cum + L:
                t = (nextat - cum)/L
                fx = x0 + (x1-x0)*t; fy = y0 + (y1-y0)*t
                nx2, ny2 = -(y1-y0)/L, (x1-x0)/L
                a = 1.9 + fR.random()*1.0          # posts lean and vary a hair
                b = 1.9 + fR.random()*1.0
                S.append(f'<line class="post" x1="{fx-nx2*a:.1f}" y1="{fy-ny2*a:.1f}"'
                         f' x2="{fx+nx2*b:.1f}" y2="{fy+ny2*b:.1f}"/>')
                nextat += 17.0 + fR.random()*7.0   # hand-set, not a ruler
            cum += L
    # bunkers: tonal face inside the shape, no line of its own
    for bply in p['bunkers']:
        P = [PX(tuple(q)) for q in bply]
        d0 = catmull(P, True)
        hh = max(q[1] for q in P)-min(q[1] for q in P)
        S.append(f'<path class="bunk" d="{d0}"/>')
        S.append(f'<path class="face" d="{catmull(scale_pts(P, 0.52, -hh*0.22), True)}"/>')
        S.append(f'<path class="bunk-o" d="{d0}"/>')
    # green: crowned — the band is the green's own outline, clipped to itself
    gP = None
    if p['green']:
        gP = [PX(tuple(q)) for q in p['green']]
        dg = catmull(gP, True)
        gx0 = min(q[0] for q in gP); gx1 = max(q[0] for q in gP)
        gy0 = min(q[1] for q in gP); gy1 = max(q[1] for q in gP)
        minor = min(gx1-gx0, gy1-gy0)
        cw = max(7, min(18, minor*0.30))
        S.append(f'<defs><clipPath id="g{hid}"><path d="{dg}"/></clipPath></defs>')
        S.append(f'<path class="fringe" d="{catmull(scale_pts(gP, 1.13), True)}"/>')
        S.append(f'<path class="grn" d="{dg}"/>')
        S.append(f'<path class="crown" clip-path="url(#g{hid})" style="stroke-width:{cw:.0f}px" d="{dg}"/>')
        S.append(f'<path class="grn-o" d="{dg}"/>')
        gx = sum(q[0] for q in gP)/len(gP); gy = sum(q[1] for q in gP)/len(gP)
        S.append(f'<circle class="cup" cx="{gx:.1f}" cy="{gy:.1f}" r="1.7"/>')
        S.append(f'<line x1="{gx:.0f}" y1="{gy:.0f}" x2="{gx:.0f}" y2="{gy-24:.0f}" class="ink"/>')
        S.append(f'<path class="flagp" d="M{gx:.0f},{gy-24:.0f} l13,4 -13,4 z"/>')
    # conifers from stands (two rows, painter's order, refuse occupied ground)
    blockers = ([gP] if gP else []) + [[PX(tuple(q)) for q in b] for b in p['bunkers']] \
               + [[PX(tuple(q)) for q in wp] for wp in p['waters']]
    def occupied(x, y, s):
        if x < 8 or x > VW-8 or y < 8 or y > VH-4: return True
        return any(pip((x, y-dy), poly) for poly in blockers for dy in (0, 9*s, 17*s, 25*s))
    treeR = random.Random(hid*7+3)
    planted = []
    fwpx = max(20, min(58, 34*sc)); rghpx = fwpx*1.55
    TREE_MIX = ['cone']*5 + ['spruce']*3 + ['broad']*2
    for st in p['stands']:
        if st['side'] == 0 and gP:
            gcx = sum(q[0] for q in gP)/len(gP); gcy = sum(q[1] for q in gP)/len(gP)
            gr = max(max(q[0] for q in gP)-gcx, gcy-min(q[1] for q in gP))
            for i in range(st['count']):
                aa = math.radians(-142+i*(104/max(1, st['count']-1))+treeR.uniform(-6, 6))
                for rr2, scl, cls in ((gr+30, 0.70, 'cone-d'), (gr+20, 0.90, 'cone')):
                    tx, ty = gcx+rr2*math.cos(aa), gcy+rr2*math.sin(aa)*0.8
                    s = scl*(0.84+treeR.random()*0.32)
                    if not occupied(tx, ty, s):
                        planted.append((tx, ty, s, cls, treeR.choice(TREE_MIX)))
        elif st['side'] != 0:
            for i in range(st['count']):
                a = st['a0']+(st['a1']-st['a0'])*(i+0.5)/st['count']
                a = max(20, min(total-15, a))
                q = point_at_arc(line, a); dx, dy = dir_at_arc(line, a)
                px0, py0 = PX(q)
                nx, ny = -dy*st['side'], dx*st['side']
                for off, scl, cls in ((rghpx/2+15, 0.70, 'cone-d'), (rghpx/2+6, 0.90, 'cone')):
                    offj = off+treeR.uniform(-4, 4)
                    tx, ty = px0+nx*offj, py0+ny*offj
                    s = scl*(0.84+treeR.random()*0.32)
                    if not occupied(tx, ty, s):
                        planted.append((tx, ty, s, cls, treeR.choice(TREE_MIX)))
    planted.sort(key=lambda t: t[1])
    for tx, ty, s, cls, kind in planted:
        S.append(cone_svg(tx, ty, s, cls, kind))
    # fescue from pack zones: clusters of long-grass tufts, planted like the
    # trees. side ±1 = a band riding outside the rough; side 0 = the carry
    # gap itself (tufts inside the corridor where the fairway hasn't started)
    tufts = []
    TUFT_MIX = ['fan']*4 + ['arc']*3 + ['sedge']*3
    def plant_tuft(tx, ty, s, cls):
        if occupied(tx, ty, 0.35): return
        if any((tx-t0)**2 + (ty-t1)**2 < 300 for t0, t1, _, _, _ in planted):
            return                        # a tuft never grows through a tree
        if any((tx-t0)**2 + (ty-t1)**2 < 130 for t0, t1, _, _, _ in tufts):
            return                        # nor on top of another tuft
        tufts.append((tx, ty, s, cls, treeR.choice(TUFT_MIX)))
    for fz in (p.get('fescue') or []):
        span = max(1.0, fz['a1'] - fz['a0'])
        # density is a MEASUREMENT, not a style: 'd' is the fraction of the
        # zone the imagery actually classifies as long grass (0..1). Thick
        # real fescue draws thick; a thin scattered patch draws thin. When no
        # measurement exists yet, 0.5 is the honest middle.
        d = min(1.0, max(0.15, fz.get('d', 0.5)))
        spacing = 44 - 34*d                  # 10 yd apart when rank, ~39 when wispy
        n = max(2, int(span / spacing))
        skip = 0.68 - 0.6*d
        for i in range(n):
            a = fz['a0'] + span*(i+0.5)/n + treeR.uniform(-6, 6)
            a = max(14, min(total-12, a))
            q = point_at_arc(line, a); dxd, dyd = dir_at_arc(line, a)
            px0, py0 = PX(q)
            if fz['side'] == 0:
                for lat in (-1, 1):
                    if treeR.random() < skip: continue
                    off = treeR.uniform(7, max(10, fwpx*0.55))
                    plant_tuft(px0 - dyd*lat*off, py0 + dxd*lat*off,
                               (0.65 + treeR.random()*0.45) * (0.72 + 0.55*d),
                               'tuft' if treeR.random() < 0.6 else 'tuft-d')
            else:
                nx, ny = -dyd*fz['side'], dxd*fz['side']
                for off, cls in ((rghpx/2 + 3, 'tuft'), (rghpx/2 + 12, 'tuft-d')):
                    if treeR.random() < skip: continue
                    offj = off + treeR.uniform(-3, 6)
                    plant_tuft(px0 + nx*offj, py0 + ny*offj,
                               (0.7 + treeR.random()*0.5) * (0.72 + 0.55*d), cls)
    for tx, ty, s, cls, kind in tufts:
        S.append(tuft_svg(tx, ty, s, cls, kind))
    # specimen trees: surveyed single trees, drawn larger — they ARE the shot
    specR = random.Random(hid * 11 + 5)
    for tp in (p.get('trees_pt') or []):
        tx, ty = PX(tuple(tp))
        S.append(cone_svg(tx, ty, 1.15 + specR.random()*0.25, 'cone',
                          specR.choice(['broad', 'broad', 'cone', 'spruce'])))
    # elevation chevrons: three fading arrows beside the approach — the
    # direction of the climb at a glance, the number stays in type
    if abs(ev0) >= 8 and par > 3 and total > 120:
        ca = max(40, total - 55)
        q = point_at_arc(line, ca); dxd, dyd = dir_at_arc(line, ca)
        base = PX(q)
        chx = base[0] - dyd*(rghpx/2 + 20)
        chy = base[1] + dxd*(rghpx/2 + 20)
        up = ev0 > 0
        glyph = 'M-4.5,2.6 L0,-2.2 L4.5,2.6' if up else 'M-4.5,-2.6 L0,2.2 L4.5,-2.6'
        for k, op in enumerate((0.9, 0.55, 0.28)):
            yy = chy + k*7*(1 if up else -1)
            S.append(f'<path class="chev" style="opacity:{op}" '
                     f'transform="translate({chx:.1f},{yy:.1f})" d="{glyph}"/>')
    # tees, real yardage spacing
    cols = ['#0C1710', '#2E6FB0', '#FFFFFF', '#A8552A']
    for i, tc in enumerate(p['tees'][:4]):
        cx, cy = PX(tuple(tc)); wd = 21-i*1.6
        S.append(f'<rect class="teebox" x="{cx-wd/2:.0f}" y="{cy-2:.0f}" width="{wd:.0f}" height="4" fill="{cols[i%4]}"/>')
    # shot line
    S.append(f'<path class="shot" d="{catmull([PX(point_at_arc(line, total*i/8)) for i in range(9)])}"/>')
    # carries last: terrain never eats a number
    for c in p['carries']:
        q = point_at_arc(line, min(c['at'], total-1)); x, y = PX(q)
        x1, x2 = x-56, x+56
        word = {'water': 'CARRY', 'fairway': 'FAIRWAY'}.get(c['kind'], 'CLEAR')
        S.append(f'<line class="carry" x1="{x1:.0f}" y1="{y:.0f}" x2="{x2:.0f}" y2="{y:.0f}"/>')
        txt = f"{c['at']} {word}"
        if x2+4+len(txt)*5.4 < VW-4:
            S.append(f'<text class="carrylab" x="{x2+4:.0f}" y="{y+3:.0f}">{txt}</text>')
        else:
            S.append(f'<text class="carrylab" x="{x1-4:.0f}" y="{y+3:.0f}" text-anchor="end">{txt}</text>')

    yd = p['yards']; depth = (yd['back']-yd['front']) if p['has_green'] else '&mdash;'
    rows = []
    if p['bend']: rows.append(('To the corner', p['bend']['at']))
    for c in p['carries']:
        rows.append(({'water': 'Carry the water', 'fairway': 'Reach the fairway'}
                     .get(c['kind'], 'Carry the fairway sand'), c['at']))
    rows += [('Front edge from the tee', yd['front']), ('Middle', yd['mid'])]
    rows = sorted(dict(rows).items(), key=lambda kv: kv[1])[:4]
    trows = ''.join(f'<tr><td>{k}</td><td class="num">{v}</td></tr>' for k, v in rows)
    ev = (p.get('facts') or {}).get('elev_ft')
    evtxt = '' if not ev else (' &middot; ' + ('&#8595;' if ev < 0 else '&#8593;')
                               + f'{abs(ev)} ft')
    # "Plays" cell: mid adjusted one yard per three feet of climb — only
    # shown when the ground actually moves
    plays = ''
    if ev and abs(ev) >= 8:
        pv = yd['mid'] + int(round(ev / 3))
        plays = (f'<div class="pl"><div class="k">Plays</div>'
                 f'<div class="v">{pv}</div></div>')
    # side-view profile strip: the real sampled ground from tee to green
    prof = ''
    ep = p.get('ep')
    if ep and len(ep) >= 6:
        w2, h2 = 296, 40
        lo, hi = min(ep), max(ep)
        rng = max(14, hi - lo)
        pts2 = [(6 + (w2-12)*i/(len(ep)-1), 7 + (h2-14)*(1 - (e-lo)/rng))
                for i, e in enumerate(ep)]
        dline = catmull(pts2)
        area = dline + f' L{pts2[-1][0]:.1f},{h2-1} L{pts2[0][0]:.1f},{h2-1} Z'
        dv = ep[-1] - ep[0]
        lab = ('&#8595;' if dv < 0 else '&#8593;') + f'{abs(dv)} ft'
        prof = (f'<div class="prof"><svg viewBox="0 0 {w2+66} {h2+4}">'
                f'<path class="pr-a" d="{area}"/><path class="pr-l" d="{dline}"/>'
                f'<circle class="pr-t" cx="{pts2[0][0]:.1f}" cy="{pts2[0][1]:.1f}" r="2.1"/>'
                f'<circle class="pr-g" cx="{pts2[-1][0]:.1f}" cy="{pts2[-1][1]:.1f}" r="2.4"/>'
                f'<text class="pr-n" x="{w2+8}" y="{h2/2+1:.0f}">{lab}</text>'
                f'<text class="pr-k" x="{w2+8}" y="{h2/2+12:.0f}">TEE &#8594; GRN</text></svg></div>')
    nav = '''<div class="nav"><div class="on"><svg viewBox="0 0 24 24"><path d="M7 21V4"/><path d="M7 5l10 2.6L7 10.4z"/></svg>Hole</div>
<div><svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2.5"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>Card</div>
<div><svg viewBox="0 0 24 24"><path d="M4 19V9M9.5 19V5M15 19v-6M20.5 19v-9"/></svg>Stats</div></div>'''
    return f'''<div class="phone">
<div class="ph-top"><div class="ph-brand">Yoink <span>CADDIE</span></div>
<div class="ph-meta">{course_name}</div></div>
<div class="hd"><div class="hd-top">
<div class="hd-id"><div class="hd-no">{hid}</div><div class="hd-spec">Par {par}<br>{yd['mid']} yds &middot; tier {p['tier']}{evtxt}</div>{'<div class="prov">PROVISIONAL &middot; GREEN SURVEYED &middot; LINE ASSUMED</div>' if p.get('synthetic') else ''}</div>
<div class="hd-dist"><div class="n num">{yd['mid']}</div><div class="u">middle</div></div></div>
<div class="fmb">
<div><div class="k">Front</div><div class="v">{yd['front']}</div></div>
<div class="on"><div class="k">Mid</div><div class="v">{yd['mid']}</div></div>
<div><div class="k">Back</div><div class="v">{yd['back']}</div></div>
<div><div class="k">Depth</div><div class="v">{depth}</div></div>
{plays}</div></div>
<svg class="holeart" viewBox="0 0 {VW} {VH}" aria-label="Hole {hid}, par {par}, {yd['mid']} yards">{''.join(S)}</svg>
{prof}<div class="strat"><div class="lbl">The read</div><p>{p['read']}</p>
<table class="carrytab">{trows}</table></div>
<div class="sign"><div class="l">{p['sign']}</div></div>
{nav}</div>'''


def render_watch(p):
    """The 41mm test: same pack, approach crop, inverted ramp."""
    line = [tuple(q) for q in p['line']]
    total = arclen(line)
    a0 = max(0, total-150)
    seg = [point_at_arc(line, a0+(total-a0)*i/10) for i in range(11)]
    # rotate so the approach plays straight up the little screen
    vx, vy = seg[-1][0]-seg[0][0], seg[-1][1]-seg[0][1]
    th = math.atan2(vx, -vy)
    cs, sn = math.cos(-th), math.sin(-th)
    rx0, ry0 = seg[0]
    def ROT(q):
        dx, dy = q[0]-rx0, q[1]-ry0
        return (rx0+dx*cs-dy*sn, ry0+dx*sn+dy*cs)
    seg = [ROT(q) for q in seg]
    green_r = [ROT(tuple(q)) for q in p['green']] if p['green'] else []
    near = lambda poly: any(math.hypot(q[0]-seg[-1][0], q[1]-seg[-1][1]) < 110 for q in poly)
    bset = [[ROT(tuple(q)) for q in b] for b in p['bunkers']]
    bset = [b for b in bset if near(b)]
    allp = list(seg) + green_r
    for b in bset: allp += list(b)
    xs = [q[0] for q in allp]; ys = [q[1] for q in allp]
    W, H, pd = 120, 84, 12
    w, h = (max(xs)-min(xs)) or 1, (max(ys)-min(ys)) or 1
    sc = min((W-2*pd)/w, (H-2*pd)/h)
    ox = (W-w*sc)/2 - min(xs)*sc; oy = (H-h*sc)/2 - min(ys)*sc
    def PX(q): return (q[0]*sc+ox, q[1]*sc+oy)
    S = []
    if p['par'] > 3:
        fw = max(9, min(24, 34*sc)); rw = fw*1.55; tw = fw*2.5
        db = catmull([PX(q) for q in seg])
        for cls, wd in (('w-tree', tw), ('w-rgh', rw), ('w-fat', fw)):
            S.append(f'<path class="{cls}" style="stroke-width:{wd:.0f}px" d="{db}"/>')
    for bply in bset:
        P = [PX(q) for q in bply]
        S.append(f'<path class="w-bunk" d="{catmull(P, True)}"/>')
    if green_r:
        gP = [PX(q) for q in green_r]
        dg = catmull(gP, True)
        S.append(f'<defs><clipPath id="gw"><path d="{dg}"/></clipPath></defs>')
        S.append(f'<path class="w-grn" d="{dg}"/>')
        S.append(f'<path class="w-crown" clip-path="url(#gw)" d="{dg}"/>')
        S.append(f'<path d="{dg}" fill="none" stroke="#0B0D0A" stroke-width="1"/>')
        gx = sum(q[0] for q in gP)/len(gP); gy = sum(q[1] for q in gP)/len(gP)
        S.append(f'<line class="w-pin" x1="{gx:.0f}" y1="{gy:.0f}" x2="{gx:.0f}" y2="{gy-12:.0f}"/>')
        S.append(f'<path class="w-flag" d="M{gx:.0f},{gy-12:.0f} l8,2.6 -8,2.6 z"/>')
    yd = p['yards']
    return f'''<div class="wcol">
<div class="watch"><div class="wface">
<div class="wtop"><span>{p['hole']} &middot; Par {p['par']}</span><span>7:52</span></div>
<div class="wbig num">{yd['mid']}</div>
<div class="wsub">Front {yd['front']} &middot; Back {yd['back']}</div>
<svg class="wart" viewBox="0 0 120 84">{''.join(S)}</svg>
<div class="wfmb">
<div><div class="k">F</div><div class="v">{yd['front']}</div></div>
<div class="on"><div class="k">Mid</div><div class="v">{yd['mid']}</div></div>
<div><div class="k">B</div><div class="v">{yd['back']}</div></div>
</div></div></div>
<p class="wcap">Same pack, watch crop, inverted ramp &mdash; hole {p['hole']}.</p>
</div>'''


CSS = ''':root{--paper:#F2F1EC;--card:#FFFFFF;--card-2:#FAFAF7;--ink:#0C1710;--ink-2:#313B33;--muted:#6D7770;--faint:#9AA39C;--forest:#14432A;--forest-d:#0A2E1C;--hair:#E3E3DC;--hair-2:#EEEEE8;--turf-1:#EDF1E7;--turf-2:#DFE8D6;--turf-3:#CBD9BE;--green-s:#B9CFA8;--green-dd:#8FAF7E;--sand:#EDE7D4;--sand-d:#DCD2B4;--water:#D8E5E6;--water-d:#B9D2D4;--wood:#C6D2BC;--wood-d:#AEBEA3;--accent:#C7F24A;--warn:#A8552A}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Archivo',sans-serif;background:var(--paper);color:var(--ink);padding:40px 20px 70px;-webkit-font-smoothing:antialiased}
.page{max-width:1180px;margin:0 auto}.num{font-variant-numeric:tabular-nums}
.mast{text-align:center;padding-bottom:26px;border-bottom:1px solid var(--hair)}
.logo{font-family:'Fraunces',Georgia,serif;font-weight:700;font-size:30px;color:var(--forest);letter-spacing:-.02em}
.logo em{font-style:normal;font-weight:400;color:var(--muted)}
.tag{font-weight:600;font-size:9.5px;letter-spacing:.26em;text-transform:uppercase;color:var(--faint);margin-top:7px}
.mast .dek{font-size:14.5px;color:var(--muted);margin:12px auto 0;max-width:52ch;line-height:1.55}
.cname{font-family:'Fraunces',Georgia,serif;font-weight:900;font-size:40px;margin-top:20px;letter-spacing:-.02em}
.cstat{font-weight:600;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-top:8px}
.cstat b{color:var(--forest-d)}
.row{display:flex;flex-wrap:wrap;gap:26px;justify-content:center;align-items:flex-start;margin-top:36px}
.phone{width:334px;background:var(--card);border:1px solid var(--hair);border-radius:26px;box-shadow:0 18px 44px rgba(12,23,16,.09),0 2px 6px rgba(12,23,16,.04);overflow:hidden;display:flex;flex-direction:column}
.ph-top{display:flex;align-items:center;justify-content:space-between;padding:13px 16px 11px;border-bottom:1px solid var(--hair-2)}
.ph-brand{font-family:'Fraunces',Georgia,serif;font-weight:700;font-size:15px;color:var(--forest);letter-spacing:-.01em}
.ph-brand span{font-family:Archivo;font-size:8.5px;font-weight:700;letter-spacing:.2em;color:var(--faint);vertical-align:2px}
.ph-meta{font-size:9.5px;font-weight:600;letter-spacing:.13em;text-transform:uppercase;color:var(--faint)}
.hd{padding:14px 16px 12px;border-bottom:1px solid var(--hair-2)}
.hd-top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.hd-id{display:flex;align-items:baseline;gap:9px}
.hd-no{font-family:'Fraunces',Georgia,serif;font-weight:700;font-size:34px;line-height:.9;color:var(--forest);letter-spacing:-.02em}
.hd-spec{font-size:10px;font-weight:600;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);line-height:1.5}
.prov{margin-top:5px;font-size:8px;font-weight:700;letter-spacing:.14em;color:#A8552A;border:1px solid #A8552A55;border-radius:4px;padding:2px 6px;display:inline-block}
.hd-dist{text-align:right;line-height:1}
.hd-dist .n{font-family:'Fraunces',Georgia,serif;font-weight:700;font-size:44px;letter-spacing:-.03em;line-height:.86}
.hd-dist .u{font-size:9.5px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin-top:5px}
.fmb{display:flex;margin-top:12px;border:1px solid var(--hair);border-radius:6px;overflow:hidden}
.fmb div{flex:1;text-align:center;padding:5px 0 6px}
.fmb div+div{border-left:1px solid var(--hair-2)}
.fmb .k{font-size:8.5px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--faint)}
.fmb .v{font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:16px;margin-top:1px}
.fmb .on{background:var(--turf-1)}.fmb .on .v{color:var(--forest)}
.holeart{display:block;width:100%;background:var(--card-2)}
.holeart .ink{stroke:var(--ink);fill:none;stroke-width:1.2;stroke-linecap:round}
.holeart .tree{stroke:var(--turf-1);fill:none;stroke-linecap:butt}
.holeart .rgh{stroke:var(--turf-2);fill:none;stroke-linecap:butt}
.holeart .fat{stroke:var(--turf-3);fill:none;stroke-linecap:butt}
.holeart .tree-o{stroke:var(--ink);fill:none;opacity:.07;stroke-linecap:butt}
.holeart .rgh-o{stroke:var(--ink);fill:none;opacity:.15;stroke-linecap:butt}
.holeart .fat-o{stroke:var(--ink);fill:none;opacity:.42;stroke-linecap:butt}
.holeart .grn{fill:var(--green-s);stroke:var(--ink);stroke-width:1.3}
.holeart .fringe{fill:var(--green-s);opacity:.4;stroke:var(--ink);stroke-width:.8;stroke-opacity:.3}
.holeart .crown{fill:none;stroke:var(--green-dd)}
.holeart .grn-o{fill:none;stroke:var(--ink);stroke-width:1.3}
.holeart .cup{fill:var(--ink);opacity:.8}
.holeart .bunk{fill:var(--sand);stroke:var(--ink);stroke-width:1.1}
.holeart .face{fill:var(--sand-d);stroke:none}
.holeart .bunk-o{fill:none;stroke:var(--ink);stroke-width:1.1}
.holeart .wat{fill:var(--water-d);stroke:var(--ink);stroke-width:1.1}
.holeart .shallow{fill:var(--water);stroke:none}
.holeart .shot{stroke:var(--forest);stroke-width:1.2;stroke-dasharray:2 4;fill:none;opacity:.7}
.holeart .disp{fill:var(--forest);opacity:.07}
.holeart .carry{stroke:var(--ink);stroke-width:.9;opacity:.5;stroke-dasharray:3 3}
.holeart .carrylab{font-family:'Archivo',sans-serif;font-weight:700;font-size:8.5px;fill:var(--ink);opacity:.85;letter-spacing:.04em;paint-order:stroke;stroke:var(--card-2);stroke-width:2.8;stroke-linejoin:round}
.holeart .arc{stroke:var(--muted);fill:none;stroke-width:.8;opacity:.2;stroke-dasharray:3 4}
.holeart .arclab{font-family:'Archivo',sans-serif;font-weight:700;font-size:7.5px;fill:var(--faint);letter-spacing:.08em}
.holeart .flagp{fill:var(--accent);stroke:var(--forest-d);stroke-width:.9}
.holeart .cone{fill:var(--wood);stroke:var(--ink);stroke-width:1;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.holeart .cone-d{fill:var(--wood-d);stroke:var(--ink);stroke-width:1;stroke-linejoin:round;stroke-opacity:.75;vector-effect:non-scaling-stroke}
.holeart .cpath{stroke:#CFC6AF;fill:none;stroke-width:2.6;stroke-dasharray:7 5;stroke-linecap:round;opacity:.8}
.holeart .bldg{fill:#DEDACD;stroke:var(--ink);stroke-opacity:.28;stroke-width:1}
.holeart .strm-o{stroke:var(--ink);fill:none;stroke-width:6;stroke-opacity:.18;stroke-linecap:round}
.holeart .strm{stroke:#9FBBC9;fill:none;stroke-width:4;stroke-linecap:round}
.holeart .rock{fill:#C7C3B8;stroke:var(--ink);stroke-width:1;stroke-linejoin:round;stroke-opacity:.55;vector-effect:non-scaling-stroke}
.holeart .rock-l{stroke:var(--ink);stroke-opacity:.35;fill:none;stroke-width:1;stroke-linecap:round;vector-effect:non-scaling-stroke}
.holeart .scree{fill:#D8D4C8;stroke:var(--ink);stroke-opacity:.3;stroke-width:1;stroke-dasharray:2.5 3}
.holeart .ridge{stroke:var(--ink);stroke-opacity:.28;stroke-width:1}
.holeart .chev{stroke:var(--forest);fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.fmb .pl{background:#F5F0E1}
.fmb .pl .v{color:#82683B}
.prof{padding:7px 16px 2px;border-top:1px solid var(--hair-2)}
.prof svg{display:block;width:100%}
.pr-a{fill:var(--turf-2);opacity:.5}
.pr-l{stroke:var(--forest);fill:none;stroke-width:1.6;stroke-linecap:round}
.pr-t{fill:var(--ink)}
.pr-g{fill:var(--accent);stroke:var(--forest-d);stroke-width:1}
.pr-n{font-family:'Fraunces',Georgia,serif;font-weight:700;font-size:12.5px;fill:var(--ink)}
.pr-k{font-family:'Archivo',sans-serif;font-weight:700;font-size:6.3px;letter-spacing:.13em;fill:var(--faint)}
.holeart .hedge{stroke:var(--wood-d);fill:none;stroke-width:3;stroke-dasharray:2.5 4.5;stroke-linecap:round}
.holeart .rail{stroke:#8A7B5E;fill:none;stroke-width:1.1;stroke-opacity:.85;stroke-linecap:round}
.holeart .post{stroke:#8A7B5E;stroke-width:1.15;stroke-opacity:.9;stroke-linecap:round}
.holeart .shed-b{fill:#E2DAC8;stroke:var(--ink);stroke-opacity:.65;stroke-width:.6;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.holeart .shed-r{fill:#CFC5B0;stroke:var(--ink);stroke-opacity:.65;stroke-width:.6;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.holeart .shed-d{fill:#C9BFA8;stroke:var(--ink);stroke-opacity:.55;stroke-width:.5;vector-effect:non-scaling-stroke}
.holeart .shed-l{stroke:var(--ink);stroke-opacity:.35;stroke-width:.4;vector-effect:non-scaling-stroke}
.holeart .tuft{stroke:#A2925A;fill:none;stroke-width:1.3;stroke-linecap:round;vector-effect:non-scaling-stroke}
.holeart .tuft-d{stroke:#877947;fill:none;stroke-width:1.3;stroke-linecap:round;stroke-opacity:.9;vector-effect:non-scaling-stroke}
.holeart .tuft-seed{fill:#A2925A}
.holeart .tuft-d-seed{fill:#877947}
.holeart .trunk{stroke:var(--ink);stroke-width:1.1;fill:none;stroke-linecap:round;stroke-opacity:.8;vector-effect:non-scaling-stroke}
.holeart .teebox{stroke:var(--ink);stroke-width:.7}
.holeart text{user-select:none}
.sign{padding:2px 16px 13px;text-align:center}
.sign .l{font-family:'Caveat',cursive;font-weight:700;font-size:18px;color:var(--muted);line-height:1.18;max-width:27ch;margin:0 auto;text-wrap:balance}
.strat{padding:12px 16px 4px;border-top:1px solid var(--hair-2)}
.strat .lbl{font-size:8.5px;font-weight:700;letter-spacing:.19em;text-transform:uppercase;color:var(--faint);margin-bottom:5px}
.strat p{font-size:12.5px;line-height:1.5;color:var(--ink-2)}
.carrytab{width:100%;border-collapse:collapse;margin:11px 0 9px}
.carrytab td{padding:5px 0;font-size:11.5px;border-bottom:1px solid var(--hair-2)}
.carrytab td:first-child{color:var(--muted)}
.carrytab td:last-child{text-align:right;font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:13px}
.carrytab tr:last-child td{border-bottom:none}
.nav{display:flex;border-top:1px solid var(--hair);background:var(--card-2);margin-top:auto}
.nav div{flex:1;text-align:center;padding:9px 0 11px;font-size:8.5px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--faint)}
.nav div.on{color:var(--forest)}
.nav svg{display:block;width:17px;height:17px;margin:0 auto 4px;stroke:currentColor;fill:none;stroke-width:1.5;stroke-linecap:round}
.wcol{display:flex;flex-direction:column;gap:11px;align-items:center;padding-top:2px}
.watch{width:198px;background:#0B0D0A;border-radius:48px;padding:12px 11px;box-shadow:0 18px 44px rgba(12,23,16,.20),0 2px 6px rgba(12,23,16,.10)}
.wface{background:#000;border-radius:37px;overflow:hidden;padding:11px 12px 10px;color:#E8EFE7}
.wtop{display:flex;align-items:center;justify-content:space-between;font-size:8px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#7C8C7B}
.wbig{font-family:'Fraunces',Georgia,serif;font-weight:700;font-size:46px;line-height:.92;letter-spacing:-.035em;margin-top:4px;color:#F2F6F0}
.wsub{font-size:9.5px;font-weight:600;color:#8FA08D;margin-top:2px;letter-spacing:.02em}
.wart{display:block;width:100%;margin:9px 0 8px;border-radius:9px;background:#070B07}
.wfmb{display:flex;border-top:1px solid #1C231B;padding-top:7px}
.wfmb div{flex:1;text-align:center}
.wfmb .k{font-size:7px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#67775F}
.wfmb .v{font-family:'Fraunces',Georgia,serif;font-weight:600;font-size:14px;color:#DDE7DA;margin-top:1px}
.wfmb .on .v{color:#C7F24A}
.wcap{font-size:10.5px;color:var(--muted);text-align:center;max-width:22ch;line-height:1.45}
.wart .w-tree{stroke:#0F160F;fill:none;stroke-linecap:butt}
.wart .w-rgh{stroke:#1B2C1F;fill:none;stroke-linecap:butt}
.wart .w-fat{stroke:#2F5236;fill:none;stroke-linecap:butt}
.wart .w-grn{fill:#54804F;stroke:#0B0D0A;stroke-width:1}
.wart .w-crown{fill:none;stroke:#2F4C35;stroke-width:6}
.wart .w-bunk{fill:#6E6647;stroke:#0B0D0A;stroke-width:.8}
.wart .w-pin{stroke:#C7F24A;stroke-width:1;fill:none}
.wart .w-flag{fill:#C7F24A}
.attr{max-width:1020px;margin:34px auto 0;text-align:center;font-size:11.5px;color:var(--muted);line-height:1.6}
.attr a{color:var(--forest)}'''


def main():
    packs = json.load(open(sys.argv[1]))
    cname = sys.argv[2] if len(sys.argv) > 2 else 'Course'
    out = sys.argv[3] if len(sys.argv) > 3 else 'caddie-crown.html'
    packs = sorted(packs, key=lambda p: p['hole'])
    cards = ''.join(render_hole(p, cname) for p in packs)
    # the watch: pick the most characterful par 4 — a severe bend if one exists
    wp = next((p for p in packs if p['par'] == 4 and p['bend'] and ((p.get('facts') or {}).get('bend') or {}).get('severe')),
              next((p for p in packs if p['par'] == 4), packs[0]))
    watch = render_watch(wp)
    par = sum(p['par'] for p in packs); yds = sum(p['yards']['mid'] for p in packs)
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Yoink Caddie &mdash; {cname} (Crown)</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700;9..144,900&family=Archivo:wght@400;500;600;700&family=Caveat:wght@500;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="page">
<div class="mast"><div class="logo">Yoink <em>Caddie</em></div>
<div class="tag">Crown build &middot; rendered from live course_holes packs</div>
<div class="cname">{cname}</div>
<div class="cstat"><b>Par {par}</b> &middot; <b class="num">{yds:,} yds</b> measured &middot; {len(packs)} holes</div>
<p class="dek">One rule holds it together: <b style="color:var(--ink);font-weight:600">the handwriting
never touches a number.</b> Every figure below was computed from the survey; every green wears its
crown; the voice gets the read and the last line.</p></div>
<div class="row">{cards}{watch}</div>
<div class="attr">Hole geometry &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (ODbL).</div>
</div></body></html>'''
    open(out, 'w').write(html)
    print('wrote', out)


if __name__ == '__main__':
    main()
