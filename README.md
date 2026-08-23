# Yoink Caddie — pipeline

Builds per-hole yardage packs for [Yoink](https://yoinkgolf.com) from open data.

- `caddie/osm.py` — Overpass fetch + normalize (OpenStreetMap, ODbL)
- `caddie/naip.py` — USDA NAIP imagery: sand detection, green corroboration, USGS 3DEP elevation
- `caddie/generate.py` — hole-local geometry, tiering, carries, hazards, facts
- `caddie/voice.py` + `caddie/signs.json` — the read and the sign-off
- `caddie/sweep.py` — catalog sweep, sharded and resumable (GEN self-upgrade)
- `caddie/crown.py` — CANONICAL design spec (Fescue Study IV) — the app renderer must match this file

Hole geometry © OpenStreetMap contributors (ODbL). Imagery: USDA NAIP / USGS 3DEP (public domain).
