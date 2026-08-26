"""Local web app for the 07709 three-market snapshot."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from tools.quant_07709.snapshot import build_snapshot


STATIC_DIR = Path(__file__).with_name("static")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class SnapshotHandler(BaseHTTPRequestHandler):
    server_version = "Quant07709Snapshot/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html")
            return
        if path == "/api/snapshot":
            self._send_json(build_snapshot())
            return
        if path == "/api/health":
            self._send_json({"ok": True, "service": "quant-07709-snapshot"})
            return
        if path.startswith("/static/"):
            relative = path[len("/static/") :]
            self._send_file(STATIC_DIR / relative)
            return
        candidate = STATIC_DIR / path.lstrip("/")
        if candidate.is_file():
            self._send_file(candidate)
            return
        self._send_json({"error": "not found", "path": path}, status=404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: object, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, path: Path) -> None:
        resolved = path.resolve()
        static_root = STATIC_DIR.resolve()
        if resolved != static_root and static_root not in resolved.parents:
            self._send_json({"error": "forbidden"}, status=403)
            return
        if not resolved.is_file():
            self._send_json({"error": "not found"}, status=404)
            return
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the 07709 three-market snapshot app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), SnapshotHandler)
    print(f"07709 snapshot app: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
