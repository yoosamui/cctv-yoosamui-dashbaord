#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STORAGE_ROOT = Path(os.environ.get("FOOTAGE_STORAGE_ROOT", "/media/share/cameras/cctv-storage"))
HOST = "127.0.0.1"
PORT = 8881
MAX_DETECTION_IMAGES = 3

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
}


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
    text = value.strip().lower()
    if not text:
        return None

    # All times are interpreted in the server's local timezone so that queries
    # match the local timestamps in the filenames (and the displayed times).
    if text == "today":
        return datetime.now()

    def time_today(value):
        # A time on its own means "today at that time", not the year 1900.
        clock = datetime.strptime(value, "%H:%M")
        return datetime.combine(datetime.now().date(), clock.time())

    # Accept [date] [time], [time], or [date]
    parts = text.split()
    if len(parts) == 1:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
            return datetime.strptime(parts[0], "%Y-%m-%d")
        if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", parts[0]):
            return time_today(parts[0][:5])
    if len(parts) >= 2:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
            try:
                return datetime.strptime(" ".join(parts[:2]), "%Y-%m-%d %H:%M")
            except ValueError:
                pass
            return datetime.strptime(parts[0], "%Y-%m-%d")
        if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", parts[0]):
            return time_today(parts[0][:5])
    return None


def group_key(path: Path) -> str:
    """Key shared by a video and its detection images.

    A video is named ``<timestamp>_<id>_<camera>.mp4`` and its detection
    images ``<timestamp>_<id>_<camera>_DETECTION_<hash>_<detection-time>.jpg``,
    so the part before ``_DETECTION`` (or the video stem) groups them together.
    Treated purely as an opaque string — no part is parsed as a time value.
    """
    name = path.name
    marker = "_DETECTION"
    if marker in name:
        return name.split(marker, 1)[0]
    return path.stem


def find_files(root: Path):
    if not root.exists():
        return []

    entries = []
    for path in root.rglob("*"):
        if path.is_file():
            entries.append((path, path.stat()))

    # Detection images only belong under an existing video. Drop "orphan"
    # images whose video has not been finalized yet (segment still recording),
    # so images never appear without their video above them.
    video_keys = {group_key(path) for path, _ in entries if file_kind(path) == "Video"}

    # Within a group, keep the video first then its detection images (by name).
    entries.sort(key=lambda item: (0 if file_kind(item[0]) == "Video" else 1, item[0].name))
    # Order groups by their shared timestamp_camera key, newest first. A stable
    # sort preserves the video-first ordering established above.
    entries.sort(key=lambda item: group_key(item[0]), reverse=True)

    results = []
    current_key = None
    images_in_group = 0
    for path, stat in entries:
        key = group_key(path)
        if key != current_key:
            current_key = key
            images_in_group = 0

        if file_kind(path) == "Image":
            if key not in video_keys:
                continue
            if images_in_group >= MAX_DETECTION_IMAGES:
                continue
            images_in_group += 1

        results.append({
                "name": path.name,
                "path": str(path),
                "camera": path.parent.name,
                "kind": file_kind(path),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "size": human_size(stat.st_size),
                "bytes": stat.st_size,
            })
    return results


def filter_results(items, since_value):
    if not since_value:
        return items

    filtered = []
    for item in items:
        modified = datetime.fromisoformat(item["modified"])
        if modified >= since_value:
            filtered.append(item)
    return filtered


def filter_today(items):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    filtered = []
    for item in items:
        modified = datetime.fromisoformat(item["modified"])
        if today <= modified < tomorrow:
            filtered.append(item)
    return filtered


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/api/preview":
            self.handle_preview(parsed, params)
            return

        query = params.get("query", [""])[0].strip()

        if parsed.path != "/api/footage":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        query_lower = query.strip().lower()
        all_items = find_files(STORAGE_ROOT)

        if query_lower == "today":
            filtered = filter_today(all_items)
            since = None
        else:
            since = parse_since(query)
            filtered = filter_results(all_items, since)

            if query and since is None:
                needle = query.lower()
                filtered = [item for item in filtered if needle in item["name"].lower() or needle in item["path"].lower()]

        payload = {
            "root": str(STORAGE_ROOT),
            "query": query,
            "count": len(filtered),
            "items": filtered,
            "since": since.isoformat() if since else None,
        }

        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def handle_preview(self, parsed, params):
        raw_path = params.get("path", [""])[0]
        if not raw_path:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing path parameter")
            return

        target = Path(raw_path)
        if not target.exists() or not target.is_file():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")
            return

        mime_type = MIME_TYPES.get(target.suffix.lower(), "application/octet-stream")
        file_size = target.stat().st_size

        # Honour HTTP range requests so the browser can seek within videos.
        start, end = self.parse_range(self.headers.get("Range"), file_size)

        if start is None:
            # No (or unsatisfiable -> treated as full) range: send the whole file.
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "public, max-age=300")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.stream_file(target, 0, file_size - 1)
            return

        length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.stream_file(target, start, end)

    @staticmethod
    def parse_range(header, file_size):
        """Parse a single-range "Range: bytes=start-end" header.

        Returns (start, end) inclusive byte offsets, or (None, None) when there
        is no range to honour (no header, malformed, or unsatisfiable).
        """
        if not header or file_size == 0:
            return None, None

        match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
        if not match:
            return None, None

        start_raw, end_raw = match.group(1), match.group(2)
        if start_raw == "" and end_raw == "":
            return None, None

        if start_raw == "":
            # Suffix range: last N bytes.
            length = int(end_raw)
            if length == 0:
                return None, None
            start = max(0, file_size - length)
            end = file_size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw != "" else file_size - 1

        end = min(end, file_size - 1)
        if start > end:
            # Unsatisfiable; fall back to a full response.
            return None, None

        return start, end

    def stream_file(self, target, start, end):
        """Write bytes [start, end] of target to the socket in chunks."""
        remaining = end - start + 1
        chunk_size = 64 * 1024
        with target.open("rb") as handle:
            handle.seek(start)
            while remaining > 0:
                chunk = handle.read(min(chunk_size, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

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
