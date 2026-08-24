# Training tracker

A list of exercises. Tap one when you do it — it stamps the date and drops to the
bottom, so whatever floated to the top is what you've been neglecting.

State lives in one JSON file on the Pi (`data/state.json`) and is mirrored into
each browser's localStorage, so the app works fully offline and syncs when it can.

## Files

| File | Role |
|---|---|
| `index.html` | The whole app — markup, CSS, logic |
| `server.py`  | Static files + `GET`/`PUT /api/state` (stdlib only) |
| `sw.js`      | Service worker — offline support |
| `manifest.webmanifest`, `icon.svg` | Home-screen install |
| `training.service` | systemd unit |
| `tests.py`   | Merge-semantics tests — run after touching `merge()` |

## 1. Install the server

> `data/` must exist before the service starts. The unit uses
> `ReadWritePaths=`, which makes systemd fail with an opaque
> `status=226/NAMESPACE` crash-loop if the directory is missing (and git does
> not track empty directories, hence `data/.gitkeep`). If you ever see that
> error: `mkdir -p ~/training/data && sudo systemctl restart training`.


    sudo cp /home/bookenpi/training/training.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now training
    systemctl status training --no-pager

Listens on 127.0.0.1:8088 only — never exposed to the LAN or the internet.

## 2. Expose over Tailscale

    sudo tailscale serve --bg 8088

Serves it at `https://<machine>.<tailnet>.ts.net` — real Let's Encrypt cert,
auto-renewing, reachable only from your tailnet. Find your exact URL with:

    tailscale status --json | grep -m1 DNSName

    tailscale serve status                 # check
    sudo tailscale serve --https=443 off   # undo

### If `tailscale serve` hangs

It needs an HTTPS certificate, which the tailnet must be configured to issue.
Check:

    tailscale status --json | grep CertDomains

`null` means certificates are off, and `serve` will hang rather than print a
useful error. Enable them in the admin console: **https://login.tailscale.com/admin/dns**
-> scroll to the bottom -> **HTTPS Certificates** -> *Enable HTTPS*. It is on
the DNS page, not under anything named "serve".

Note: enabling this publishes your machine names to public Certificate
Transparency logs. It leaks the name, not access — the machine stays
tailnet-only.

## 3. On your phone

1. Connect Tailscale on the phone — it must be signed in to the same tailnet.
2. Open the URL, then Chrome menu -> "Add to Home screen".

The dot in the header is sync status: green synced, amber syncing, grey offline,
red failed. Tapping exercises works regardless — it syncs when it can.

## How sync avoids losing data

Clients PUT their whole state; the server *merges* rather than overwrites, and
returns the merged result for the client to adopt. So:

- A device offline for a week cannot erase what happened meanwhile.
- `history` is append-only, so unioning it is always safe.
- Undo writes a tombstone into `removed`, because a plain union would otherwise
  hand the undone entry straight back on the next sync.
- Deletes and renames use `deleted` / `updated` (last-write-wins on `updated`).

Writes are atomic (`tmp` + `os.replace`), so a crash mid-write leaves the
previous file intact.

    python3 tests.py     # 15 assertions covering the above

## Updating the app

Edit `index.html`, then bump `CACHE = "training-v2"` in `sw.js` to v3, v4, ...
so installed phones pick up the new version instead of the cached one.

    sudo systemctl restart training

## Backups

    cp ~/training/data/state.json ~/state-$(date +%F).json

Or Menu -> Export backup in the app. Import *merges*, so restoring an old backup
won't wipe newer entries.
