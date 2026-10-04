"""Dev bridge: serve the lab UI and stream a live ledger run over SSE.

TEMPORARY. The core lane (Ish) owns the real SSE server on top of
Ledger.subscribe; when it lands, point the UI at it with ?sse=<its url> and
delete this file. It exists so the UI can follow a real Omnigent run today.

    .venv/bin/python ui/live_server.py --port 8766
    # http://localhost:8766/ui/?sse=/events?run=<run_id>
    # http://localhost:8766/runs   -> JSON list of run ids in the ledger

Reads the same ledger as tools/forge_emit.py ($FORGE_LEDGER_DB or
results/ledger.db). Its only write is POST /api/approve: a human decision on a
P6 gate (GATE_RESOLVED), which tools/forge_gate.py is waiting on.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cli.approve import resolve  # noqa: E402
from core.ledger import Ledger  # noqa: E402


HEARTBEAT = 5.0  # seconds; a failed heartbeat write is how a closed client is noticed


class Server(ThreadingHTTPServer):
    daemon_threads = True


class Handler(SimpleHTTPRequestHandler):
    ledger: Ledger  # one shared instance, created once in main()

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/runs":
            return self._json(self.ledger.runs())
        if url.path == "/events":
            return self._sse(parse_qs(url.query))
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        # The only write the UI may make: a human decision on a P6 gate.
        if urlparse(self.path).path != "/api/approve":
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            e = resolve(self.ledger, body["run_id"], body["gate_id"], body.get("decision") == "approve", via="lab-ui")
            return self._json({"ok": True, "seq": e["seq"], "status": e["payload"]["status"]})
        except (SystemExit, KeyError, ValueError) as err:
            body = json.dumps({"ok": False, "error": str(err)}).encode()
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, q):
        run = (q.get("run") or [""])[0]
        after = int((q.get("after") or ["0"])[0])
        if not run:
            self.send_error(400, "run is required")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        last_write = time.monotonic()
        try:
            while True:
                for event in self.ledger.read(run, after_seq=after):
                    after = event["seq"]
                    self.wfile.write(f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n".encode())
                    last_write = time.monotonic()
                if time.monotonic() - last_write >= HEARTBEAT:
                    self.wfile.write(b": keepalive\n\n")
                    last_write = time.monotonic()
                self.wfile.flush()
                time.sleep(0.3)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, *args):
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--db", default=None)
    a = p.parse_args(argv)
    Handler.ledger = Ledger(a.db) if a.db else Ledger()
    server = Server(("127.0.0.1", a.port), partial(Handler, directory=str(ROOT)))
    print(f"FORGE live bridge on http://localhost:{a.port}/ui/  (ledger: {a.db or 'default'})")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
