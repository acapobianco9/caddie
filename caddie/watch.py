#!/usr/bin/env python3
"""Watch the Yoink alert engine from outside it.

This lives in the PUBLIC caddie repo on purpose. The old watchdog sat in the
private yoink repo, so when GitHub billing lapsed on 29 Aug 2026 it stopped
running silently -- the one failure a watchdog exists to survive. Public repos
get free Actions minutes, so this one keeps running when that one cannot.

It also needs NO secrets. Every table it reads is exposed through row-level
security to the publishable key that already ships in the app's page source,
so there is nothing here worth stealing and nothing to leak in a public log.

Three checks, and the second is the one the old watchdog could not do:

  1. STALLED  -- newest snapshot older than STALL_MIN. The engine is down.
  2. DARK     -- individual courses that have returned nothing for DARK_H.
                 The old version compared now against max(last_nonempty_at)
                 across ALL courses, so a single healthy course anywhere kept
                 it quiet. Eight Long Island courses sat dark for nine days
                 without a peep. This checks each course on its own.
  3. GAPS     -- a live course missing a day from the middle of its own
                 booking window, which means a partial fetch overwrote a good
                 snapshot. Santapogue Creek held Aug 29 and Aug 31 with Aug 30
                 missing while dropping 94 times to 69 in 100 seconds.

Exits non-zero when something is wrong, which makes the Actions run fail, and
GitHub emails on a failed run. That is the whole notification path -- no ntfy
topic, no Resend key, no admin address to keep in sync.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

SB   = "https://qjynukromzfoimrnjfuk.supabase.co/rest/v1/"
KEY  = os.environ.get("SB_PUBLISHABLE",
                      "sb_publishable_4HJbhlWLC4FANHyAEaqFdA_OfriYyjF")

STALL_MIN = int(os.environ.get("STALL_MIN", "40"))
DARK_H    = int(os.environ.get("DARK_H", "48"))
DARK_MAX  = int(os.environ.get("DARK_MAX", "4"))   # tolerated dark courses
GAP_MAX   = int(os.environ.get("GAP_MAX", "6"))    # tolerated gappy courses


def get(path):
    req = urllib.request.Request(
        SB + path, headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def parse(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    now = dt.datetime.now(dt.timezone.utc)
    snaps = get("snapshots?select=course_key,updated_at,last_nonempty_at,times")
    if not snaps:
        print("FAIL  no snapshot rows at all")
        return 1

    problems = []

    # ---- 1. is the engine running at all -------------------------------
    newest = max((parse(s["updated_at"]) for s in snaps if s.get("updated_at")),
                 default=None)
    age = (now - newest).total_seconds() / 60 if newest else 1e9
    if age > STALL_MIN:
        problems.append(f"ENGINE STALLED - newest snapshot is {age:.0f} min old")
    print(f"engine    newest snapshot {age:.0f} min old "
          f"({'stalled' if age > STALL_MIN else 'ok'})")

    # ---- 2. courses dark on their own ----------------------------------
    dark = []
    for s in snaps:
        ln = parse(s.get("last_nonempty_at"))
        if ln is None:
            continue                      # never had times; not a regression
        hours = (now - ln).total_seconds() / 3600
        if hours > DARK_H:
            dark.append((s["course_key"], round(hours / 24, 1)))
    dark.sort(key=lambda x: -x[1])
    print(f"dark      {len(dark)} course(s) empty > {DARK_H}h")
    for k, d in dark[:20]:
        print(f"            {k}  {d} days")
    if len(dark) > DARK_MAX:
        problems.append(f"{len(dark)} courses dark (tolerating {DARK_MAX})")

    # ---- 3. partial fetches: a hole in the middle of a window ----------
    gappy = []
    for s in snaps:
        times = s.get("times") or []
        if not times:
            continue
        days = sorted({t.get("date") for t in times if t.get("date")})
        if len(days) < 3:
            continue
        first = dt.date.fromisoformat(days[0])
        last = dt.date.fromisoformat(days[-1])
        span = (last - first).days + 1
        missing = span - len(days)
        if missing > 0:
            gappy.append((s["course_key"], missing))
    gappy.sort(key=lambda x: -x[1])
    print(f"gaps      {len(gappy)} course(s) missing interior days")
    for k, m in gappy[:20]:
        print(f"            {k}  {m} day(s) missing")
    if len(gappy) > GAP_MAX:
        problems.append(f"{len(gappy)} courses with partial sheets "
                        f"(tolerating {GAP_MAX})")

    print()
    if problems:
        for p in problems:
            print("FAIL  " + p)
        return 1
    print("OK    engine live, coverage healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
