#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STORAGE_ROOT = Path("/media/pi/share/cameras/cctv-storage")
HOST = "127.0.0.1"
PORT = 8881

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "Video"
    if suffix in IMAGE_EXTENSIONS:
        return "Image"
    return "File"


def parse_since(value: str):
    text = value.strip()
    if not text:
        return None

    # Accept --since [date] [time] or --since [time] or --since [date]
    parts = text.split()
    if len(parts) == 1:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
            return datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", parts[0]):
            return datetime.strptime(parts[0], "%H:%M").replace(tzinfo=timezone.utc)
    if len(parts) >= 2:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
            try:
                return datetime.strptime(" ".join(parts[:2]), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            return datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", parts[0]):
            return datetime.strptime(parts[0], "%H:%M").replace(tzinfo=timezone.utc)
    return None


def find_files(root: Path):
    if not root.exists():
        return []

    results = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            results.append({
                "name": path.name,
                "path": str(path),
                "camera": path.parent.name,
                "kind": file_kind(path),
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                "size": human_size(stat.st_size),
            })
    return results


def filter_results(items, since_value):
    if not since_value:
        return items

    filtered = []
    for item in items:
        modified = datetime.fromisoformat(item["modified"].replace("Z", "+00:00")).astimezone(timezone.utc)
        if modified >= since_value:
            filtered.append(item)
    return filtered


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        query = params.get("query", [""])[0].strip()

        if parsed.path != "/api/footage":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        since = None
        if "--since" in query:
            parts = query.split()
            try:
                idx = parts.index("--since")
                since_text = " ".join(parts[idx + 1:])
                since = parse_since(since_text)
            except Exception:
                since = None

        all_items = find_files(STORAGE_ROOT)
        filtered = filter_results(all_items, since)

        if query and "--since" not in query:
            needle = query.lower()
            filtered = [item for item in filtered if needle in item["name"].lower() or needle in item["path"].lower()]

        payload = {
            "root": str(STORAGE_ROOT),
            "query": query,
            "count": len(filtered),
            "items": filtered,
            "since": since.isoformat().replace("+00:00", "Z") if since else None,
        }

        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
        print(f"Footage API listening on http://{HOST}:{PORT}/api/footage")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping footage API...")
    except OSError as exc:
        print(f"Could not start footage API: {exc}", file=sys.stderr)
        sys.exit(1)
