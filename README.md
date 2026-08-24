# exercise-tracker

A gym tracker built around one question: **what haven't I done in a while?**

Tap an exercise when you do it. It stamps the date and drops to the bottom of
the list. Whatever has floated to the top is what you've been neglecting — so
the list *is* the recommendation, with no plan to configure and no schedule to
fall behind on.

Runs on a Raspberry Pi, reachable from anywhere over Tailscale. No database, no
build step, no dependencies outside the Python standard library.

```
┌──────────────────────────────┐
│ Training      4 done today ● │
├──────────────────────────────┤
│ Overhead press         never │  ← never done
│ Pull-ups             12 days │  ← neglected
│ Deadlift              8 days │
│ Squat                 3 days │
│ Bench press          2 days  │
│ Dips                   today │  ← just tapped, sinks to the bottom
└──────────────────────────────┘
```

Day counts are colour-coded — green under 3 days, amber under a week, red past
that, purple for never — so staleness is readable at a glance rather than
something you have to compute.

## Design

**Offline first.** `localStorage` is the rendering source of truth, so the app
opens instantly and works with no signal — which matters in a gym basement. A
service worker caches the shell. The server is a merge point it pushes to and
adopts from, never something it blocks on.

**The server merges, it does not overwrite.** Clients `PUT` their whole state;
the server returns the merged result for the client to adopt. That makes every
push idempotent and safe to retry, and rules out two failure modes that a
naive "PUT overwrites the file" backend ships with by default:

- *A stale device silently erasing history.* Your phone caches state, sits
  offline for a week, reconnects, and pushes — wiping everything the laptop
  logged meanwhile. Merging makes this impossible: `history` is append-only,
  so unioning it is always safe.
- *Undo being resurrected.* If a mis-tap syncs before you hit UNDO, a union
  merge hands the timestamp straight back on the next sync. So undo writes a
  tombstone into `removed`, and the merge subtracts those. Deletes and renames
  use the same idea (`deleted` / last-write-wins on `updated`).

**Durability.** Writes are atomic — temp file, `fsync`, `rename` — so a power
cut mid-write leaves the previous state intact rather than a truncated file.

## Layout

| File | Role |
|---|---|
| `index.html` | The whole app — markup, CSS, logic |
| `server.py` | Static files + `GET`/`PUT /api/state`, stdlib only |
| `sw.js` | Service worker, offline support |
| `manifest.webmanifest`, `icon.svg` | Home-screen install |
| `training.service` | systemd unit template |
| `tests.py` | Merge-semantics tests |
| `SETUP.md` | Full install and hosting guide |

State lives in one file, `data/state.json` (gitignored):

```json
{"version": 2, "exercises": [
  {"id": "sq", "name": "Squat", "history": ["2026-08-25T17:00:00.000Z"],
   "removed": [], "updated": 1756142400000, "deleted": false}
]}
```

## Quick start

```sh
git clone https://github.com/Alexander-Bokedal/exercise-tracker.git
cd exercise-tracker
mkdir -p data
python3 server.py          # http://127.0.0.1:8088
```

For the Pi + Tailscale setup — systemd unit, HTTPS, installing to your phone's
home screen — see **[SETUP.md](SETUP.md)**.

## Tests

```sh
python3 tests.py
```

Covers stale-device overwrite, offline merge, undo tombstones, rename
last-write-wins, delete tombstones, malformed input, and idempotency.

## Scope

Deliberately small. No accounts, no auth, no sets, no reps, no weights, no
charts. Access control is Tailscale's job — the server binds `127.0.0.1` and
has no login of its own, so **do not expose it to the internet directly**.

## License

MIT — see [LICENSE](LICENSE).
