#!/usr/bin/env python3
"""Training tracker: static files + a single-JSON-file state store.

Writes are merged, not overwritten, so a device that has been offline for a
week cannot clobber what happened meanwhile. Bind to localhost and put
`tailscale serve` in front of it; there is no auth here on purpose.
"""

import json
import os
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data", "state.json")
PORT = int(os.environ.get("PORT", "8088"))

# Whitelist rather than path resolution — no traversal surface at all.
STATIC = {
    "/":                     ("index.html",          "text/html; charset=utf-8"),
    "/index.html":           ("index.html",          "text/html; charset=utf-8"),
    "/sw.js":                ("sw.js",               "text/javascript; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/icon.svg":             ("icon.svg",            "image/svg+xml"),
}

MAX_BODY      = 2_000_000
MAX_EXERCISES = 500
MAX_HISTORY   = 5_000
MAX_NAME      = 100
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z?$")

lock = threading.Lock()


# ---------------------------------------------------------------- persistence

def read_state():
    try:
        with open(DATA, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"version": 2, "exercises": []}
    except (json.JSONDecodeError, OSError) as e:
        # Never silently start from empty — that would look like data loss.
        print(f"!! cannot read {DATA}: {e}", file=sys.stderr, flush=True)
        raise


def write_state(state):
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(DATA), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, DATA)          # atomic: a crash leaves the old file intact
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------- merge

def clean_stamps(seq):
    if not isinstance(seq, list):
        return set()
    return {s for s in seq if isinstance(s, str) and ISO.match(s)}


def merge(base, incoming):
    """Union of both sides, per exercise id.

    history is append-only, so unioning it is always safe. `removed` carries
    explicit tombstones for undone entries — without it, a union would happily
    resurrect anything the user undid. Names use last-write-wins on `updated`.
    """
    out = {}
    for e in base.get("exercises", []):
        if isinstance(e, dict) and isinstance(e.get("id"), str):
            out[e["id"]] = e

    for inc in incoming.get("exercises", [])[:MAX_EXERCISES]:
        if not isinstance(inc, dict):
            continue
        eid = inc.get("id")
        if not isinstance(eid, str) or not eid:
            continue

        cur = out.get(eid, {})
        removed = clean_stamps(cur.get("removed")) | clean_stamps(inc.get("removed"))
        history = (clean_stamps(cur.get("history")) | clean_stamps(inc.get("history"))) - removed

        inc_u = inc.get("updated") if isinstance(inc.get("updated"), (int, float)) else 0
        cur_u = cur.get("updated") if isinstance(cur.get("updated"), (int, float)) else 0
        win = inc if inc_u >= cur_u else cur

        name = win.get("name") if isinstance(win.get("name"), str) else "?"
        out[eid] = {
            "id": eid,
            "name": name.strip()[:MAX_NAME] or "?",
            "history": sorted(history)[-MAX_HISTORY:],
            "removed": sorted(removed)[-MAX_HISTORY:],
            "updated": max(inc_u, cur_u),
            "deleted": bool(win.get("deleted", False)),
        }

    return {"version": 2, "exercises": list(out.values())[:MAX_EXERCISES]}


# -------------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    server_version = "training"

    def log_message(self, fmt, *args):
        pass  # journald gets the important lines from print() instead

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if not cache:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/state":
            try:
                with lock:
                    state = read_state()
            except Exception:
                return self._json(500, {"error": "state unreadable"})
            return self._json(200, state)

        entry = STATIC.get(path)
        if not entry:
            return self._send(404, b"not found")
        name, ctype = entry
        try:
            with open(os.path.join(BASE, name), "rb") as f:
                return self._send(200, f.read(), ctype)
        except OSError:
            return self._send(404, b"not found")

    do_HEAD = do_GET

    def do_PUT(self):
        if self.path.split("?", 1)[0] != "/api/state":
            return self._send(404, b"not found")

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._json(400, {"error": "bad length"})
        if length <= 0 or length > MAX_BODY:
            return self._json(413, {"error": "bad body size"})

        try:
            incoming = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, {"error": "invalid json"})
        if not isinstance(incoming, dict) or not isinstance(incoming.get("exercises"), list):
            return self._json(400, {"error": "expected {exercises: []}"})

        try:
            with lock:
                merged = merge(read_state(), incoming)
                write_state(merged)
        except Exception as e:
            print(f"!! write failed: {e}", file=sys.stderr, flush=True)
            return self._json(500, {"error": "write failed"})

        # Hand back the merged truth so the client adopts it verbatim.
        return self._json(200, merged)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    print(f"training: http://127.0.0.1:{PORT}  data={DATA}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
