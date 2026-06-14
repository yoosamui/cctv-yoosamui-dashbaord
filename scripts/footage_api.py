#!/usr/bin/env python3
"""
CCTV Footage API Server v1.0.0
"""

import json
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ============================================
# CONFIGURATION - CHANGE THIS IF NEEDED
# ============================================
STORAGE_ROOT = Path("/media/share/cameras/cctv-storage")
HOST = "0.0.0.0"  # Listen on all network interfaces
PORT = 8881
MAX_ITEMS_PER_PAGE = 50
# ============================================

def get_all_files():
    """Get all video and image files."""
    if not STORAGE_ROOT.exists():
        print(f"ERROR: {STORAGE_ROOT} does not exist")
        return []
    
    files = []
    count = 0
    for path in STORAGE_ROOT.rglob("*"):
        if path.is_file():
            name = path.name
            suffix = path.suffix.lower()
            
            # Only process videos and images
            if suffix in {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}:
                # Extract timestamp from filename
                timestamp = None
                match = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', name)
                if match:
                    date_str = match.group(1)
                    time_str = match.group(2).replace('-', ':')
                    try:
                        timestamp = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                    except:
                        pass
                
                # Extract camera name
                camera = "Unknown"
                parts = name.replace('.mp4', '').replace('.jpg', '').split('_')
                if len(parts) >= 3:
                    camera = parts[2]
                
                # Determine type
                kind = "Video" if suffix in {'.mp4', '.mov', '.mkv', '.avi', '.webm'} else "Image"
                
                files.append({
                    "name": name,
                    "path": str(path),
                    "camera": camera,
                    "kind": kind,
                    "timestamp": timestamp,
                    "size_bytes": path.stat().st_size,
                })
                count += 1
                if count % 1000 == 0:
                    print(f"Loaded {count} files...")
    
    # Sort by timestamp (oldest first)
    files.sort(key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min)
    print(f"Total files loaded: {len(files)}")
    return files

# Load files at startup
print("Loading files from storage...")
ALL_FILES = get_all_files()
print(f"Ready! Found {len(ALL_FILES)} files.")

def parse_query(query: str):
    """Parse query into (camera_name, filter1, filter2, text_search)."""
    if not query:
        return None, None, None, None
    
    original = query.strip()
    words = original.split()
    
    # Check for camera name
    camera_name = None
    remaining = original
    
    available_cameras = set(f["camera"] for f in ALL_FILES)
    camera_map = {cam.lower(): cam for cam in available_cameras}
    
    if words and words[0].lower() in camera_map:
        camera_name = camera_map[words[0].lower()]
        remaining = ' '.join(words[1:]) if len(words) > 1 else ""
    
    if not remaining:
        return camera_name, None, None, None
    
    # Check for "today"
    if remaining.lower() == 'today':
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start.replace(hour=23, minute=59, second=59)
        return camera_name, today_start, today_end, None
    
    # Check for time only: HH:MM or HH-MM
    time_match = re.match(r'^(\d{2})[:-](\d{2})$', remaining)
    if not time_match:
        time_match = re.match(r'^(\d{2})$', remaining)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return camera_name, f"{hour:02d}:{minute:02d}", None, None
    
    # Check for date only: YYYY-MM-DD
    date_match = re.match(r'^(\d{4}-\d{2}-\d{2})$', remaining)
    if date_match:
        start_dt = datetime.strptime(remaining, "%Y-%m-%d")
        end_dt = start_dt.replace(hour=23, minute=59, second=59)
        return camera_name, start_dt, end_dt, None
    
    # Check for date + time
    match = re.match(r'^(\d{4}-\d{2}-\d{2})[:\s-](\d{2})[:-](\d{2})$', remaining)
    if match:
        date_str = match.group(1)
        hour = match.group(2)
        minute = match.group(3)
        start_dt = datetime.strptime(f"{date_str} {hour}:{minute}:00", "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(f"{date_str} 23:59:59", "%Y-%m-%d %H:%M:%S")
        return camera_name, start_dt, end_dt, None
    
    # Everything else is text search
    return camera_name, None, None, remaining

def filter_files(files, camera_name, filter1, filter2, text_search):
    """Apply all filters to files."""
    result = files
    
    # Filter by camera
    if camera_name:
        result = [f for f in result if f["camera"].lower() == camera_name.lower()]
    
    # Filter by datetime range
    if filter1 and filter2 and isinstance(filter1, datetime):
        result = [f for f in result if f["timestamp"] and filter1 <= f["timestamp"] <= filter2]
    
    # Filter by time on latest date
    elif filter1 and isinstance(filter1, str) and ":" in filter1:
        try:
            hour, minute = map(int, filter1.split(':'))
            time_obj = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
            
            # Find the latest date with files at or after this time
            latest_date = None
            for f in result:
                if f["timestamp"] and f["timestamp"].time() >= time_obj:
                    if latest_date is None or f["timestamp"].date() > latest_date:
                        latest_date = f["timestamp"].date()
            
            if latest_date:
                start_dt = datetime.combine(latest_date, time_obj)
                end_dt = datetime.combine(latest_date, datetime.max.time().replace(hour=23, minute=59, second=59))
                result = [f for f in result if f["timestamp"] and start_dt <= f["timestamp"] <= end_dt]
            else:
                result = []
        except:
            pass
    
    # Filter by text search
    if text_search:
        needle = text_search.lower()
        result = [f for f in result if needle in f["name"].lower()]
    
    # Sort by timestamp (oldest first)
    result.sort(key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min)
    
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        if parsed.path == "/api/footage":
            query = params.get("query", [""])[0].strip()
            page = int(params.get("page", ["1"])[0])
            
            # Parse and filter
            camera_name, filter1, filter2, text_search = parse_query(query)
            filtered = filter_files(ALL_FILES, camera_name, filter1, filter2, text_search)
            
            # Paginate
            start = (page - 1) * MAX_ITEMS_PER_PAGE
            end = start + MAX_ITEMS_PER_PAGE
            paginated = filtered[start:end]
            total_pages = (len(filtered) + MAX_ITEMS_PER_PAGE - 1) // MAX_ITEMS_PER_PAGE if filtered else 0
            
            # Prepare response
            items = []
            for f in paginated:
                items.append({
                    "name": f["name"],
                    "path": f["path"],
                    "camera": f["camera"],
                    "kind": f["kind"],
                    "modified": f["timestamp"].isoformat() if f["timestamp"] else "",
                    "size": f"{f['size_bytes'] / 1024 / 1024:.1f} MB",
                    "bytes": f["size_bytes"],
                })
            
            cameras = sorted(set(f["camera"] for f in ALL_FILES))
            
            response = {
                "version": "1.0.0",
                "root": str(STORAGE_ROOT),
                "query": query,
                "camera_filter": camera_name,
                "available_cameras": cameras,
                "total_files": len(ALL_FILES),
                "total_filtered": len(filtered),
                "page": page,
                "total_pages": total_pages,
                "items_per_page": MAX_ITEMS_PER_PAGE,
                "count": len(items),
                "items": items,
            }
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response, indent=2).encode())
            
        elif parsed.path == "/api/preview":
            raw_path = params.get("path", [""])[0]
            if raw_path:
                target = Path(raw_path)
                if target.exists() and target.is_file():
                    mime_type = "video/mp4" if target.suffix.lower() == '.mp4' else "image/jpeg"
                    self.send_response(200)
                    self.send_header("Content-Type", mime_type)
                    self.send_header("Content-Length", str(target.stat().st_size))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    with open(target, "rb") as f:
                        self.wfile.write(f.read())
                    return
            
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            
        elif parsed.path == "/api/version":
            response = {"version": "1.0.0", "name": "CCTV Footage API"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
    
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print("=" * 50)
    print("CCTV Footage API Server v1.0.0")
    print("=" * 50)
    print(f"Storage: {STORAGE_ROOT}")
    print(f"Listening: http://{HOST}:{PORT}/api/footage")
    print(f"Total files loaded: {len(ALL_FILES)}")
    print(f"Items per page: {MAX_ITEMS_PER_PAGE}")
    print("=" * 50)
    
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
        server.serve_forever()
    except OSError as e:
        print(f"ERROR: Cannot bind to {HOST}:{PORT}")
        print(f"Reason: {e}")
        print("Try changing HOST to '127.0.0.1' or check if port is already in use")
