#!/usr/bin/env python3
"""The Caddie voice.

Two jobs, two registers, one rule: the handwriting never touches a number.

THE READ (straight type, beside the numbers): composed from geometry facts —
bend, carries, water behaviour, sand, green depth, and course-context ranks —
with multiple phrasings per fact. Selection is seeded per course, and a
variant used once on a card is not used again on that card, so no two holes
on a course read alike and no two courses read identically.

THE SIGN (handwriting, after the decision): drawn from caddie/signs.json — a
tagged library built to grow. Lines are picked by hole traits, never repeated
within a course, seeded so a course always signs the same way.
"""
import json, os, random

_SIGNS = None
def _signs():
    global _SIGNS
    if _SIGNS is None:
        path = os.path.join(os.path.dirname(__file__), 'signs.json')
        _SIGNS = json.load(open(path))
    return _SIGNS


# ---------------------------------------------------------------- the read

def _pick(rng, used, variants, **kw):
    """Pick a variant not yet used on this card (fall back to any)."""
    pool = [v for v in variants if v not in used] or variants
    v = rng.choice(pool)
    used.add(v)
    return v.format(**kw)

# --- tee-shot sentences, by situation ---

BEND = [
    "Bends {dir} at {at}.",
    "The corner comes at {at}, turning {dir}.",
    "Doglegs {dir} — the elbow is {at} out.",
    "Everything sets up off the {dir} turn at {at}.",
    "A {dir}-hand turn at {at}; position beats power to the corner.",
]
BEND_SAND = [
    "Bends {dir} at {at}, and the {sside} sand on the corner holds on until {bfar}.",
    "The {dir} turn at {at} is guarded — corner sand on the {sside}, gone at {bfar}.",
    "Doglegs {dir} at {at} with sand waiting on the inside; {bfar} flies it all.",
]
BEND_HARD = [
    "A hard {dir} turn at {at} — there is no cutting this one, so don't audition for it.",
    "Bends {dir} at {at}, and properly. Play to the corner and take the new angle.",
]
CROSS3 = [
    "All carry — the water is done at {wat}.",
    "The water lets go at {wat}. After that it's just golf.",
    "One swing over water; it's finished at {wat}.",
    "Everything short of {wat} is wet, and nothing after it is.",
]
CROSS45 = [
    "The water crosses you — clear at {wat}.",
    "You cross water once, and it's over at {wat}.",
    "The creek cuts the hole; {wat} sees you over it.",
    "Water across the line — done with it at {wat}.",
]
CROSS_TWICE = [
    "The water crosses you twice — {w1} clears the first, {w2} the second.",
    "Two crossings on this one: {w1}, then again at {w2}. Count them both.",
]
LATERAL = [
    "Water rides the {wside} side most of the way; favour the other half of the corridor.",
    "The {wside} edge is wet from tee to green — live on the {other} half and this is easy.",
    "Everything leaking {wside} feeds the water. The {other} side is free real estate.",
    "Water for a partner down the {wside}. It only matters if you flirt with it.",
]
KEY_BUNKER = [
    "The {sside} bunker at {bnear} is the only question off the tee.",
    "One bunker matters here — {sside} side, starting {bnear} out.",
    "Sand at {bnear} on the {sside}: fly it or stay under it, just decide on the tee.",
    "Off the tee it's a single conversation — the {sside} sand at {bnear}.",
]
PLAIN = [
    "Straight away. Pick a window and swing.",
    "No tricks off the tee — pick your line and commit.",
    "As honest as they come; hit it straight and it stays simple.",
    "Nothing hidden. The hole is exactly what it looks like from the tee.",
    "Fairway, green, no arguments. Make your pass.",
]
FWSTART = [
    "The fairway doesn't start until {at} — everything short of it is scrub.",
    "It's {at} just to reach the short grass. Budget for it.",
    "Nothing but rough for the first {at}; the fairway begins where it ends.",
    "The carry to the fairway is {at}. That's the first number that matters.",
    "Short grass starts at {at} — anything less is a walk in the wild stuff.",
]
RANK = [
    "The longest hole on the card — plan the third shot before the first.",
    "Longest par {par} out here; par feels like a birdie.",
    "Shortest par {par} of the day — greed is permitted, within reason.",
    "The shortest hole on the card. Take dead aim.",
]
NO_TRICKS3 = [
    "No tricks. The number is the number; commit to it.",
    "One number, one swing. Believe the middle.",
    "Nothing between you and the green but yardage.",
    "Flat, honest, measurable. Trust the club in your hand.",
]
LAT3 = [
    "The water keeps you company down the {wside} — it only matters if you get cute.",
    "Water on the {wside}, but it's a spectator unless you invite it in.",
]

# Water down BOTH sides. There is no "other half" to favour, so these never
# offer one -- the old sentences did, and on 52 of 291 sampled holes they
# pointed at the lake.
LATERAL_BOTH = [
    "Water down both sides \u2014 there is no bail-out here, only the fairway.",
    "It is wet left and wet right; staying between them is the whole plan.",
    "Both edges are water. Take whatever club keeps you in the corridor.",
]
LAT3_BOTH = [
    "Water either side of this one \u2014 the green is the only dry miss.",
    "Wet left, wet right. Hit the green or take your medicine.",
]

# Trees, measured (GEN 10). A chute is timber inside 60 yards on BOTH sides
# for most of the walk; a squeeze is one side only. Neither sentence carries
# a number, because the number is on the card.
CHUTE = [
    "Trees both sides the whole way \u2014 this one is a chute, so the tee shot is the hole.",
    "It is timber left and timber right. Find the corridor or spend the hole punching out.",
    "The trees close in on both sides; there is no wide miss here, only a straight one.",
    "A proper avenue \u2014 both edges are lined, and the fairway is the only room you get.",
]
CHUTE3 = [
    "Trees tight either side \u2014 take the club that keeps you between them.",
    "The gap is the green. Both sides are timber, so miss short rather than wide.",
]
TREE_SIDE = [
    "The timber squeezes the {tside}; everything you own is on the {tother}.",
    "Trees crowd the {tside} side, which makes the {tother} half the safe half.",
    "Favour the {tother} \u2014 the {tside} is lined, and a shot in there is a chip out.",
]

# --- approach / green sentences ---

DEEP = [
    "The green is {depth} deep, so the front number matters more than the pin.",
    "{depth} yards of green front to back — club for the half you want, not the flag.",
    "A {depth}-deep green: front and back are a full club apart. Choose on purpose.",
]
SHALLOW = [
    "Shallow green — only {depth} deep. Land it soft or use the fringe.",
    "Just {depth} deep up top; this one rewards precision over muscle.",
    "The green is a ribbon — {depth} deep. Spin it or run it, but pick one.",
]
MID = [
    "Green runs {depth} deep; middle is never wrong.",
    "{depth} deep and honest up top — center of the green walks away happy.",
    "Nothing sneaky at the green: {depth} deep, take the middle and go putt.",
]
GSIDE_WATER = [
    "Water at the green; short {wside} is wet.",
    "The green sits against water on the {wside} — long beats short all day.",
    "Miss anywhere but short {wside}; that one costs a ball.",
]
GSIDE_SAND = [
    "Sand guards the green on the {gside}; the open side is the {gother}.",
    "Greenside sand {gside} — favour the {gother} half coming in.",
    "The {gside} miss is a bunker; the {gother} miss is a chip. Choose accordingly.",
]
NO_GREEN = [
    "The survey runs thin here; the yardage doesn't. Play the number.",
    "No mapped green — trust the middle number and commit.",
]
LAYUP = [
    "The layup squeezes past sand at {bnear} — stay short of it or fly it, nothing in between.",
    "Sand pinches the layup at {bnear}; pick your distance before you pick your club.",
    "The second shot has one job: miss the sand that starts at {bnear}.",
]


def compose_read(facts, rng, used):
    """facts: dict from generate.py — see _facts(). Returns 1–2 sentences."""
    s = []
    f = facts
    other = {'left': 'right', 'right': 'left'}
    # --- sentence 1: the tee shot ---
    if f['par'] == 3:
        if f.get('cross'):
            s.append(_pick(rng, used, CROSS3, wat=f['cross'][0]))
        elif f.get('gside_water'):
            pass  # let the green sentence carry it
        elif f.get('lateral') == 'both':
            s.append(_pick(rng, used, LAT3_BOTH))
        elif f.get('lateral'):
            s.append(_pick(rng, used, LAT3, wside=f['lateral']))
        elif f.get('chute_pct', 0) >= 55:
            s.append(_pick(rng, used, CHUTE3))
        else:
            s.append(_pick(rng, used, NO_TRICKS3))
    else:
        if f.get('fw_start'):
            s.append(_pick(rng, used, FWSTART, at=f['fw_start']))
        if f.get('cross') and len(f['cross']) >= 2:
            s.append(_pick(rng, used, CROSS_TWICE, w1=f['cross'][0], w2=f['cross'][1]))
        elif f.get('bend') and f.get('corner_sand'):
            s.append(_pick(rng, used, BEND_SAND, dir=f['bend']['dir'], at=f['bend']['at'],
                           sside=f['corner_sand']['side'], bfar=f['corner_sand']['far']))
        elif f.get('bend') and f['bend'].get('severe'):
            s.append(_pick(rng, used, BEND_HARD, dir=f['bend']['dir'], at=f['bend']['at']))
        elif f.get('bend'):
            s.append(_pick(rng, used, BEND, dir=f['bend']['dir'], at=f['bend']['at']))
        elif f.get('cross'):
            s.append(_pick(rng, used, CROSS45, wat=f['cross'][0]))
        elif f.get('lateral') == 'both':
            s.append(_pick(rng, used, LATERAL_BOTH))
        elif f.get('lateral'):
            s.append(_pick(rng, used, LATERAL, wside=f['lateral'], other=other[f['lateral']]))
        elif f.get('chute_pct', 0) >= 55:
            s.append(_pick(rng, used, CHUTE))
        elif f.get('tree_side'):
            s.append(_pick(rng, used, TREE_SIDE, tside=f['tree_side'],
                           tother=other[f['tree_side']]))
        elif f.get('key_bunker'):
            s.append(_pick(rng, used, KEY_BUNKER, sside=f['key_bunker']['side'],
                           bnear=f['key_bunker']['near']))
        elif f.get('layup_sand'):
            s.append(_pick(rng, used, LAYUP, bnear=f['layup_sand']['near']))
        elif f.get('rank'):
            s.append(_pick(rng, used, [v for v in RANK if
                           ('longest' in v) == (f['rank'] == 'longest')], par=f['par']))
        else:
            s.append(_pick(rng, used, PLAIN))
        # second crossing rides along with a bend
        if f.get('bend') and f.get('cross') and len(s) == 1 and len(f['cross']) == 1:
            s.append(_pick(rng, used, CROSS45, wat=f['cross'][0]))
        elif f.get('bend') and f.get('lateral') == 'both' and len(s) == 1:
            s.append(_pick(rng, used, LATERAL_BOTH))
        elif f.get('bend') and f.get('lateral') and len(s) == 1:
            s.append(_pick(rng, used, LATERAL, wside=f['lateral'], other=other[f['lateral']]))
    # --- sentence 2: the approach / green ---
    if len(s) < 2:
        if f.get('gside_water'):
            s.append(_pick(rng, used, GSIDE_WATER, wside=f['gside_water']))
        elif f.get('gside_sand'):
            s.append(_pick(rng, used, GSIDE_SAND, gside=f['gside_sand'],
                           gother=other[f['gside_sand']]))
        elif not f['has_green']:
            s.append(_pick(rng, used, NO_GREEN))
        elif f['depth'] >= 30:
            s.append(_pick(rng, used, DEEP, depth=f['depth']))
        elif f['depth'] <= 16:
            s.append(_pick(rng, used, SHALLOW, depth=f['depth']))
        else:
            s.append(_pick(rng, used, MID, depth=f['depth']))
    return ' '.join(s[:2])


# ---------------------------------------------------------------- the sign

def _trait_buckets(facts, is_last, is_first):
    f = facts
    b = []
    if is_last: b.append('finisher')
    if is_first: b.append('opener')
    if f['par'] == 3:
        if f.get('cross') or f.get('gside_water'): b.append('par3_water')
        if f['total'] > 200: b.append('par3_long')
        if f['total'] < 130: b.append('par3_short')
        b.append('par3')
    if f['par'] == 4:
        if f['total'] > 440: b.append('par4_long')
        if f['total'] < 310: b.append('par4_short')
        b.append('par4')
    if f['par'] == 5:
        if f['total'] > 560: b.append('par5_monster')
        b.append('par5')
    if f.get('cross') or f.get('lateral') or f.get('gside_water'):
        b.append('river' if f.get('water_is_river') else 'pond')
        b.append('water')
    if f.get('sand_count', 0) >= 5: b.append('sand_heavy')
    if f.get('chute_pct', 0) >= 55: b.append('chute')
    if f.get('stands'): b.append('trees')
    if not (f.get('cross') or f.get('lateral') or f.get('key_bunker') or f.get('bend')):
        b.append('honest')
    b.append('any')
    return b


def pick_sign(facts, rng, used_signs, is_last=False, is_first=False):
    lib = _signs()
    for bucket in _trait_buckets(facts, is_last, is_first):
        pool = [l for l in lib.get(bucket, []) if l not in used_signs]
        if pool:
            line = rng.choice(pool)
            used_signs.add(line)
            return line
    return 'middle of the green is never wrong.'


def make_course_voice(course_key):
    """Returns (rng, used_reads, used_signs) seeded stably per course."""
    seed = sum(ord(c) * (i + 7) for i, c in enumerate(course_key)) & 0x7fffffff
    return random.Random(seed), set(), set()
