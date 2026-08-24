#!/usr/bin/env python3
"""Yoink watchdog (alert-only) - runs on the public caddie repo where Actions
is free, because the private repo's Actions are billing-blocked.

One check: the engine's newest snapshot write. If it is older than STALL_MIN
minutes, the engine on the VPS has stalled - ping the admin's ntfy topic and
fail the run so the workflow shows red. This watchdog does NOT try to restart
anything (the old restart path dispatched the retired Actions engine); it makes
sure a stall is LOUD instead of silent.
"""
import datetime as dt, json, os, sys, urllib.request

SB = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ['SUPABASE_SERVICE_KEY']
H = {'apikey': KEY, 'Authorization': 'Bearer ' + KEY}
STALL_MIN = 25
ADMIN = 'anthony@amg-demolition.com'


def get(path):
    req = urllib.request.Request(SB + '/rest/v1/' + path, headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    rows = get('snapshots?select=updated_at&order=updated_at.desc&limit=1')
    if not rows:
        print('[watchdog] no snapshots at all')
        sys.exit(1)
    ts = rows[0]['updated_at'].replace('Z', '+00:00')
    newest = dt.datetime.fromisoformat(ts)
    age = dt.datetime.now(dt.timezone.utc) - newest
    mins = age.total_seconds() / 60
    print(f'[watchdog] newest snapshot {mins:.1f} min old')
    if mins <= STALL_MIN:
        return
    # stalled: shout on ntfy, then fail the run
    prof = get(f'profiles?select=ntfy_topic&email=eq.{ADMIN}')
    topic = prof and prof[0].get('ntfy_topic')
    if topic:
        body = (f'Yoink engine looks STALLED - newest scan is '
                f'{int(mins)} min old. Check the VPS.').encode()
        req = urllib.request.Request(f'https://ntfy.sh/{topic}', data=body,
                                     headers={'Title': 'Yoink watchdog',
                                              'Priority': 'high',
                                              'Tags': 'rotating_light'})
        urllib.request.urlopen(req, timeout=30)
        print('[watchdog] pinged ntfy')
    sys.exit(1)


if __name__ == '__main__':
    main()
