#!/usr/bin/env python3
"""PodPanel - a small pod-side web panel for ComfyUI-Ultimate.

Three jobs, on their own port:

  1. An interactive gallery of everything in the output directory (images,
     videos and audio), with filters, search and a lightbox.
  2. One-click downloads - single files, or a zip of everything you tick.
  3. A drop-in runner: drag a PodPreset ``setup.sh`` onto the page (or paste
     one) and it runs on the pod with the output streamed live.

Standard library only, so it runs on the image's Python or any python3 you
happen to have. Pillow and ffmpeg are used when present (they are both in this
image) to make thumbnails; without them the gallery still works, it just serves
originals and shows placeholder tiles for video.

Because it has no imports outside the stdlib, this single file can also be
dropped onto an already-running pod and started by hand:

    python3 /workspace/podpanel.py --port 8090 &

The image starts it automatically; see scripts/start.sh.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.0"

# --------------------------------------------------------------------- config
OUTPUT_ROOT = "/workspace/output"
WORKDIR = "/workspace/model-setup"
THUMB_DIR = "/tmp/podpanel-thumbs"
RUN_CWD = "/workspace"
TOKEN = ""
RUNNER_ENABLED = True
SCAN_TTL = 3.0

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif", ".tiff"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}
AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg", ".opus", ".m4a", ".aac"}

PIL = None
FFMPEG = None


def _detect_tools() -> None:
    global PIL, FFMPEG
    try:
        from PIL import Image  # type: ignore
        PIL = Image
    except Exception:
        PIL = None
    FFMPEG = shutil.which("ffmpeg")


# ---------------------------------------------------------------------- utils
def slugify(text: str, fallback: str = "preset") -> str:
    out = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip()).strip("-._")
    out = re.sub(r"-{2,}", "-", out)
    return out[:64] or fallback


def kind_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    return ""


def under(root: str, rel: str):
    """Resolve rel under root, or None if it would escape (traversal guard)."""
    rel = urllib.parse.unquote(rel or "").lstrip("/\\")
    root_real = os.path.realpath(root)
    full = os.path.realpath(os.path.join(root_real, rel))
    if full != root_real and not full.startswith(root_real + os.sep):
        return None
    return full


# --------------------------------------------------------------------- gallery
_scan_lock = threading.Lock()
_scan_cache = {"at": 0.0, "items": []}


def scan_output(force: bool = False) -> list:
    """Every media file under OUTPUT_ROOT, newest first. Cached for a few seconds."""
    now = time.time()
    with _scan_lock:
        if not force and now - _scan_cache["at"] < SCAN_TTL:
            return _scan_cache["items"]
    items = []
    root = os.path.realpath(OUTPUT_ROOT)
    if os.path.isdir(root):
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if name.startswith("."):
                    continue
                full = os.path.join(base, name)
                kind = kind_of(name)
                if not kind:
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                items.append({
                    "path": rel,
                    "name": name,
                    "dir": os.path.dirname(rel),
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "kind": kind,
                })
    items.sort(key=lambda i: i["mtime"], reverse=True)
    with _scan_lock:
        _scan_cache["at"] = time.time()
        _scan_cache["items"] = items
    return items


def thumb_path(item: dict):
    """A cached thumbnail for an item, or None if one cannot be made.

    Failures are cached too: without that, every page load would re-shell
    ffmpeg for a video it can never decode.
    """
    os.makedirs(THUMB_DIR, exist_ok=True)
    key = hashlib.sha1(f"{item['path']}|{int(item['mtime'])}".encode()).hexdigest()
    out = os.path.join(THUMB_DIR, key + ".jpg")
    miss = os.path.join(THUMB_DIR, key + ".none")
    if os.path.isfile(out):
        return out
    if os.path.isfile(miss):
        return None

    def gave_up():
        try:
            open(miss, "w").close()
        except OSError:
            pass
        return None

    src = under(OUTPUT_ROOT, item["path"])
    if not src or not os.path.isfile(src):
        return gave_up()
    try:
        if item["kind"] == "image" and PIL is not None:
            im = PIL.open(src)
            im.draft("RGB", (480, 480))
            im = im.convert("RGB")
            im.thumbnail((420, 420))
            im.save(out, "JPEG", quality=82)
        elif item["kind"] == "video" and FFMPEG:
            subprocess.run(
                [FFMPEG, "-y", "-ss", "1", "-i", src, "-frames:v", "1",
                 "-vf", "scale=420:-2", out],
                capture_output=True, timeout=30)
        elif item["kind"] == "image":
            return src          # no Pillow: let the browser scale the original
        else:
            return gave_up()
    except Exception:
        return gave_up()
    return out if os.path.isfile(out) else gave_up()


# ----------------------------------------------------------------------- jobs
class Job:
    def __init__(self, jid, name, script, log, status="queued", created=None):
        self.id = jid
        self.name = name
        self.script = script
        self.log = log
        self.status = status
        self.created = created or time.time()
        self.started = None
        self.ended = None
        self.exit_code = None
        self.proc = None

    def meta(self) -> dict:
        return {
            "id": self.id, "name": self.name, "status": self.status,
            "created": self.created, "started": self.started, "ended": self.ended,
            "exit_code": self.exit_code, "script": os.path.basename(self.script),
            "log_size": os.path.getsize(self.log) if os.path.isfile(self.log) else 0,
        }


JOBS: dict = {}
JOBS_LOCK = threading.Lock()
RUN_QUEUE: "queue.Queue[str]" = queue.Queue()


def upload_dir() -> str:
    """Derived at call time: a module-level constant would freeze the default
    workdir and quietly ignore --workdir."""
    return os.path.join(WORKDIR, "uploads")


def job_sidecar(job: Job) -> str:
    return os.path.splitext(job.script)[0] + ".json"


def save_job(job: Job) -> None:
    try:
        os.makedirs(upload_dir(), exist_ok=True)
        with open(job_sidecar(job), "w", encoding="utf-8") as fh:
            json.dump(job.meta(), fh)
    except OSError:
        pass


def load_history() -> None:
    """Previous runs, so the panel still lists them after a pod reboot."""
    where = upload_dir()
    if not os.path.isdir(where):
        return
    for name in sorted(os.listdir(where)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(where, name), encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            continue
        jid = meta.get("id")
        if not jid or jid in JOBS:
            continue
        script = os.path.join(where, meta.get("script") or "")
        log = os.path.splitext(script)[0] + ".log"
        job = Job(jid, meta.get("name") or jid, script, log,
                  status=meta.get("status") or "unknown", created=meta.get("created"))
        job.started = meta.get("started")
        job.ended = meta.get("ended")
        job.exit_code = meta.get("exit_code")
        if job.status == "running":
            job.status = "interrupted"     # the server died mid-run
        JOBS[jid] = job


def new_job(name: str, content: str) -> Job:
    where = upload_dir()
    os.makedirs(where, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    jid = f"{stamp}-{hashlib.sha1(f'{name}{time.time()}'.encode()).hexdigest()[:4]}"
    slug = slugify(name or "preset")
    script = os.path.join(where, f"{jid}-{slug}.sh")
    log = os.path.join(where, f"{jid}-{slug}.log")
    with open(script, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.chmod(script, 0o755)
    # newline="\n" everywhere: text mode would turn every line ending into \r\n
    # on Windows, which is both ugly in the log and shifts byte offsets.
    with open(log, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# PodPanel run {jid} - {name}\n# script: {script}\n\n")
    job = Job(jid, name or slug, script, log)
    with JOBS_LOCK:
        JOBS[jid] = job
    save_job(job)
    return job


def worker_loop() -> None:
    """One preset at a time: these downloads are heavy and share a volume."""
    while True:
        jid = RUN_QUEUE.get()
        try:
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job or job.status == "killed":
                continue
            job.status = "running"
            job.started = time.time()
            save_job(job)
            env = dict(os.environ)
            env.setdefault("PODPANEL", "1")
            for key, value in (job.__dict__.get("env") or {}).items():
                env[key] = value
            # /workspace is where the volume and ComfyUI live, but fall back to
            # the script's own directory rather than refusing to start.
            cwd = RUN_CWD if os.path.isdir(RUN_CWD) else os.path.dirname(job.script)
            with open(job.log, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"# started {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                fh.write(f"# cwd: {cwd}\n\n")
                fh.flush()
                try:
                    job.proc = subprocess.Popen(
                        ["bash", job.script], cwd=cwd, env=env,
                        stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
                    code = job.proc.wait()
                except OSError as exc:
                    fh.write(f"\n# could not start: {exc}\n")
                    code = 127
            job.exit_code = code
            job.ended = time.time()
            if job.status != "killed":
                job.status = "ok" if code == 0 else "failed"
            with open(job.log, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"\n# finished {time.strftime('%Y-%m-%d %H:%M:%S')} "
                         f"(exit {code})\n")
            job.proc = None
            save_job(job)
        except Exception as exc:                        # never kill the worker
            try:
                with open(job.log, "a", encoding="utf-8") as fh:
                    fh.write(f"\n# PodPanel error: {exc}\n")
                job.status = "failed"
                job.ended = time.time()
                save_job(job)
            except Exception:
                pass
        finally:
            RUN_QUEUE.task_done()


# --------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = f"PodPanel/{VERSION}"
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):
        sys.stderr.write("[podpanel] %s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def _text(self, text, status=200, ctype="text/html; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def _authorised(self, query) -> bool:
        if not TOKEN:
            return True
        given = (query.get("token", [""])[0]
                 or self.headers.get("X-PodPanel-Token", "")
                 or self._cookie_token())
        return given == TOKEN

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "podpanel_token":
                return value
        return ""

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # -- file serving -----------------------------------------------------
    def _send_file(self, path, download=False, ctype=None):
        try:
            st = os.stat(path)
        except OSError:
            return self._json({"error": "not found"}, 404)
        if not os.path.isfile(path):
            return self._json({"error": "not a file"}, 404)
        ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
        size = st.st_size
        start, end, status = 0, max(size - 1, 0), 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes=") and size:
            spec = rng[6:].split(",")[0].strip()
            first, _, last = spec.partition("-")
            try:
                if first:
                    start = int(first)
                    end = int(last) if last else size - 1
                else:
                    start = max(0, size - int(last))
                    end = size - 1
            except ValueError:
                start, end = 0, size - 1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end = min(end, size - 1)
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if download:
            safe = os.path.basename(path).replace('"', "")
            quoted = urllib.parse.quote(os.path.basename(path))
            self.send_header("Content-Disposition",
                             f'attachment; filename="{safe}"; filename*=UTF-8\'\'{quoted}')
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if getattr(self, "_head_only", False):
            return
        try:
            with open(path, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    chunk = fh.read(min(262144, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # -- routes -----------------------------------------------------------
    def do_HEAD(self):
        """Same routes as GET, headers only: curl -I and some clients use it."""
        self._head_only = True
        self.do_GET()

    def do_GET(self):
        parts = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parts.path)
        query = urllib.parse.parse_qs(parts.query)

        if path == "/api/health":
            return self._json({
                "ok": True, "version": VERSION,
                "output_root": OUTPUT_ROOT, "exists": os.path.isdir(OUTPUT_ROOT),
                "pillow": PIL is not None, "ffmpeg": bool(FFMPEG),
                "runner": RUNNER_ENABLED, "auth": bool(TOKEN),
            })

        if not self._authorised(query):
            if path == "/":
                return self._text(LOGIN_PAGE, 401)
            return self._json({"error": "bad or missing token"}, 401)

        if path == "/":
            return self._text(PAGE)
        if path == "/favicon.ico":
            return self._text("", 204, "image/x-icon")

        if path == "/api/items":
            force = query.get("refresh", ["0"])[0] == "1"
            items = scan_output(force)
            kind = query.get("kind", ["all"])[0]
            folder = query.get("dir", [""])[0]
            text = query.get("q", [""])[0].strip().lower()
            if kind and kind != "all":
                items = [i for i in items if i["kind"] == kind]
            if folder:
                items = [i for i in items if i["dir"] == folder or
                         i["dir"].startswith(folder.rstrip("/") + "/")]
            if text:
                items = [i for i in items if text in i["name"].lower()]
            try:
                offset = max(0, int(query.get("offset", ["0"])[0]))
                limit = min(500, max(1, int(query.get("limit", ["60"])[0])))
            except ValueError:
                offset, limit = 0, 60
            dirs = {}
            for i in scan_output():
                dirs[i["dir"]] = dirs.get(i["dir"], 0) + 1
            return self._json({
                "total": len(items),
                "offset": offset,
                "items": items[offset:offset + limit],
                "dirs": sorted(({"dir": d, "count": c} for d, c in dirs.items()),
                               key=lambda x: x["dir"]),
                "all_total": len(scan_output()),
                "bytes_total": sum(i["size"] for i in scan_output()),
            })

        if path == "/api/jobs":
            with JOBS_LOCK:
                jobs = [j.meta() for j in JOBS.values()]
            jobs.sort(key=lambda j: j["created"], reverse=True)
            return self._json({"jobs": jobs, "runner": RUNNER_ENABLED})

        if path == "/api/job":
            jid = query.get("id", [""])[0]
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job:
                return self._json({"error": "no such job"}, 404)
            try:
                offset = max(0, int(query.get("offset", ["0"])[0]))
            except ValueError:
                offset = 0
            chunk = ""
            try:
                # Binary, so the offset is a true byte offset whatever line
                # endings the child process happened to write.
                with open(job.log, "rb") as fh:
                    fh.seek(offset)
                    raw = fh.read(262144)
                chunk = raw.decode("utf-8", errors="replace")
                offset += len(raw)
            except OSError:
                pass
            meta = job.meta()
            meta["offset"] = offset
            meta["chunk"] = chunk
            return self._json(meta)

        if path.startswith("/media/") or path.startswith("/download/") \
                or path.startswith("/thumb/"):
            route, _, rel = path.lstrip("/").partition("/")
            item = next((i for i in scan_output() if i["path"] == rel), None)
            if not item:
                return self._json({"error": "not found"}, 404)
            if route == "thumb":
                tp = thumb_path(item)
                if not tp:
                    return self._json({"error": "no thumbnail"}, 404)
                # No forced type: a generated thumb is a .jpg, but without
                # Pillow the fallback is the original file and keeps its own.
                return self._send_file(tp)
            full = under(OUTPUT_ROOT, rel)
            if not full:
                return self._json({"error": "bad path"}, 400)
            return self._send_file(full, download=(route == "download"))

        return self._json({"error": "no such route"}, 404)

    def do_POST(self):
        parts = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parts.path)
        query = urllib.parse.parse_qs(parts.query)
        if not self._authorised(query):
            return self._json({"error": "bad or missing token"}, 401)
        body = self._body()

        if path == "/api/run":
            if not RUNNER_ENABLED:
                return self._json({"error": "the runner is disabled on this pod"}, 403)
            content = body.get("content") or ""
            if not content.strip():
                return self._json({"error": "nothing to run - drop a .sh file first"}, 400)
            name = (body.get("name") or "preset").strip()
            job = new_job(name, content)
            env = {}
            if body.get("civitai_key"):
                env["CIVITAI_API_KEY"] = body["civitai_key"]
            if body.get("hf_token"):
                env["HF_TOKEN"] = body["hf_token"]
            job.__dict__["env"] = env
            RUN_QUEUE.put(job.id)
            return self._json({"job": job.meta(), "queued": RUN_QUEUE.qsize()})

        if path == "/api/job/kill":
            jid = body.get("id") or ""
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job:
                return self._json({"error": "no such job"}, 404)
            job.status = "killed"
            if job.proc and job.proc.poll() is None:
                try:
                    job.proc.terminate()
                except OSError:
                    pass
            save_job(job)
            return self._json({"job": job.meta()})

        if path == "/api/zip":
            names = body.get("paths") or []
            items = {i["path"]: i for i in scan_output()}
            chosen = [items[n] for n in names if n in items]
            if not chosen:
                return self._json({"error": "nothing selected"}, 400)
            label = slugify(body.get("name") or "outputs")
            return self._stream_zip(chosen, label)

        return self._json({"error": "no such route"}, 404)

    def _stream_zip(self, items, label):
        """Stream a zip without a temp file: media is already compressed, so
        every member goes in stored, and zipfile copes with a write-only sink."""
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{label}.zip"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

        class Sink:
            """zipfile writes through _Tellable, which does `offset += fp.write(...)`,
            so write() must return the byte count or every member is lost."""

            def __init__(self, write):
                self._write = write

            def write(self, data):
                self._write(data)
                return len(data)

            def flush(self):
                pass

        try:
            with zipfile.ZipFile(Sink(self.wfile.write), "w", zipfile.ZIP_STORED,
                                 allowZip64=True) as zf:
                for item in items:
                    full = under(OUTPUT_ROOT, item["path"])
                    if not full or not os.path.isfile(full):
                        continue
                    zf.write(full, arcname=item["path"])
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            sys.stderr.write(f"[podpanel] zip failed: {exc}\n")
        self.close_connection = True


# ------------------------------------------------------------------ web page
PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PodPanel</title>
<link rel="icon" href="data:,">
<style>
:root{--bg:#0e1116;--panel:#161b22;--panel-2:#1c232c;--line:#2a323d;--text:#e6edf3;
--dim:#8b98a5;--accent:#4c8dff;--accent-2:#2f6fe0;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 18px;border-bottom:1px solid var(--line);
background:var(--panel);position:sticky;top:0;z-index:20;flex-wrap:wrap}
h1{font-size:16px;margin:0;display:flex;align-items:center;gap:9px}
.logo{background:var(--accent);color:#fff;border-radius:7px;width:26px;height:26px;display:grid;
place-items:center;font-size:12px;font-weight:700}
.spacer{flex:1}
nav{display:flex;gap:6px}
nav button{background:transparent;border:1px solid transparent;color:var(--dim);padding:6px 12px;
border-radius:8px;cursor:pointer;font-size:13px}
nav button.active{background:var(--panel-2);color:var(--text);border-color:var(--line)}
button,input,select,textarea{font:inherit;color:var(--text)}
button{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:7px 12px;
cursor:pointer}
button:hover:not(:disabled){border-color:var(--accent)}
button:disabled{opacity:.45;cursor:not-allowed}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.primary:hover:not(:disabled){background:var(--accent-2)}
button.danger{color:var(--bad)}
input,select,textarea{background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:7px 10px}
textarea{width:100%;font-family:ui-monospace,Consolas,monospace;font-size:12px}
main{padding:16px 18px 60px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.chips{display:flex;gap:6px}
.chip{border-radius:999px;padding:5px 12px;font-size:12.5px;background:var(--panel-2);
border:1px solid var(--line);cursor:pointer;color:var(--dim)}
.chip.active{background:var(--accent);border-color:var(--accent);color:#fff}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(190px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;
position:relative;cursor:pointer;transition:border-color .12s}
.card:hover{border-color:var(--accent)}
.card.sel{border-color:var(--accent);box-shadow:0 0 0 2px rgba(76,141,255,.35)}
.card .thumb{aspect-ratio:1;background:#0b0f14;display:grid;place-items:center;overflow:hidden}
.card .thumb img{width:100%;height:100%;object-fit:cover;display:block}
.card .ph{color:var(--dim);font-size:26px}
.card .meta{padding:7px 9px;border-top:1px solid var(--line)}
.card .nm{font-size:12px;word-break:break-all;line-height:1.35}
.card .sub{font-size:11px;color:var(--dim);margin-top:2px;display:flex;justify-content:space-between;gap:6px}
.card .tick{position:absolute;top:7px;left:7px;width:19px;height:19px;accent-color:var(--accent);
cursor:pointer;opacity:.92}
.card .kind{position:absolute;top:7px;right:7px;background:#000a;border-radius:6px;padding:2px 7px;
font-size:10.5px;letter-spacing:.04em;text-transform:uppercase}
.empty{color:var(--dim);padding:40px 0;text-align:center}
.pill{background:var(--panel-2);border:1px solid var(--line);border-radius:999px;padding:2px 9px;
font-size:11.5px;color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:500;font-size:12px}
.badge{border-radius:999px;padding:2px 9px;font-size:11.5px;border:1px solid var(--line)}
.badge.ok{color:var(--ok);border-color:var(--ok)}
.badge.bad{color:var(--bad);border-color:var(--bad)}
.badge.run{color:var(--accent);border-color:var(--accent)}
.badge.queue{color:var(--warn);border-color:var(--warn)}
.log{background:#0b0f14;border:1px solid var(--line);border-radius:10px;padding:12px;
font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:pre-wrap;word-break:break-word;
max-height:60vh;overflow:auto;margin-top:12px}
.drop{border:2px dashed var(--line);border-radius:12px;padding:26px;text-align:center;color:var(--dim);
cursor:pointer;transition:border-color .12s,background .12s}
.drop.hot{border-color:var(--accent);background:rgba(76,141,255,.06);color:var(--text)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;
margin-bottom:16px}
.panel h2{font-size:14px;margin:0 0 10px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
label.f{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--dim)}
.hint{color:var(--dim);font-size:12px}
#lightbox{position:fixed;inset:0;background:#000c;z-index:60;display:none;place-items:center;padding:24px}
#lightbox.on{display:grid}
#lightbox .box{background:var(--panel);border:1px solid var(--line);border-radius:12px;max-width:94vw;
max-height:92vh;display:flex;flex-direction:column;overflow:hidden}
#lightbox .stage{background:#000;display:grid;place-items:center;overflow:auto;min-height:220px}
#lightbox img,#lightbox video{max-width:90vw;max-height:74vh;display:block}
#lightbox audio{width:min(70vw,620px);margin:30px}
#lightbox .foot{padding:10px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;
border-top:1px solid var(--line)}
#lightbox .nav{position:absolute;top:50%;transform:translateY(-50%);font-size:22px;padding:10px 14px}
#lbPrev{left:18px}#lbNext{right:18px}
[hidden]{display:none!important}
</style>
</head>
<body>
<header>
  <h1><span class="logo">PP</span> PodPanel</h1>
  <span id="stats" class="pill">loading…</span>
  <div class="spacer"></div>
  <nav>
    <button id="tabOut" class="active">Outputs</button>
    <button id="tabRun">Run a preset</button>
  </nav>
</header>

<main>
  <section id="viewOut">
    <div class="bar">
      <div class="chips">
        <span class="chip active" data-kind="all">All</span>
        <span class="chip" data-kind="image">Images</span>
        <span class="chip" data-kind="video">Videos</span>
        <span class="chip" data-kind="audio">Audio</span>
      </div>
      <select id="dirFilter"><option value="">All folders</option></select>
      <input id="search" type="search" placeholder="filter by name…" style="min-width:180px">
      <div class="spacer"></div>
      <button id="selAll">Select all</button>
      <button id="selNone">Clear</button>
      <button id="zipBtn" class="primary" disabled>Download selected</button>
      <button id="refresh">Refresh</button>
    </div>
    <div id="grid" class="grid"></div>
    <div id="more" class="bar" hidden><button id="moreBtn">Load more</button>
      <span id="shown" class="hint"></span></div>
    <div id="noOut" class="empty" hidden>Nothing in the output folder yet. Generate something in ComfyUI.</div>
  </section>

  <section id="viewRun" hidden>
    <div class="panel">
      <h2>1. Give it a preset script</h2>
      <div id="drop" class="drop">Drop a <b>setup.sh</b> from PodPreset here, or click to choose a file<br>
        <span class="hint">it runs on this pod with bash, from /workspace</span></div>
      <input id="file" type="file" accept=".sh,text/x-shellscript,text/plain" hidden>
      <div class="row" style="margin-top:12px">
        <label class="f">Name <input id="runName" placeholder="preset name" style="min-width:200px"></label>
        <label class="f">CivitAI key (optional, this run only)
          <input id="civKey" type="password" placeholder="CIVITAI_API_KEY"></label>
        <label class="f">HF token (optional, this run only)
          <input id="hfKey" type="password" placeholder="HF_TOKEN"></label>
      </div>
      <p class="hint">Keys are passed to the script as environment variables for this run and are never
        written to disk. The script never contains them either.</p>
      <details style="margin-top:8px"><summary class="hint">or paste the script</summary>
        <textarea id="paste" rows="6" placeholder="#!/usr/bin/env bash&#10;…"></textarea></details>
      <div class="row" style="margin-top:12px">
        <button id="runBtn" class="primary" disabled>Run it</button>
        <span id="runMsg" class="hint"></span>
      </div>
    </div>
    <div class="panel">
      <h2>2. Runs <span id="jobCount" class="pill">0</span></h2>
      <table><thead><tr><th>Name</th><th>Status</th><th>Started</th><th>Took</th>
        <th>Exit</th><th></th></tr></thead><tbody id="jobs"></tbody></table>
      <div id="noJobs" class="hint">No runs yet.</div>
    </div>
    <div class="panel" id="logPanel" hidden>
      <h2>Log <span id="logName" class="pill"></span>
        <button id="logRefresh" style="float:right">Refresh</button>
        <button id="killBtn" class="danger" style="float:right;margin-right:6px">Stop</button></h2>
      <div id="log" class="log"></div>
    </div>
  </section>
</main>

<div id="lightbox">
  <button class="nav" id="lbPrev">‹</button>
  <div class="box">
    <div class="stage" id="lbStage"></div>
    <div class="foot">
      <span id="lbName" style="flex:1;word-break:break-all"></span>
      <span id="lbMeta" class="hint"></span>
      <button id="lbCopy">Copy path</button>
      <button id="lbDown" class="primary">Download</button>
      <button id="lbClose">Close</button>
    </div>
  </div>
  <button class="nav" id="lbNext">›</button>
</div>

<script>
const $ = (id) => document.getElementById(id);
const state = {items:[], total:0, offset:0, limit:60, kind:"all", dir:"", q:"",
               selected:new Set(), lb:0, job:null, logOffset:0, poll:null};
const LIMIT = 60;

function human(n){n=Number(n)||0;const u=["B","KiB","MiB","GiB","TiB"];let i=0;
  while(n>=1024&&i<u.length-1){n/=1024;i++}return i?`${n.toFixed(2)} ${u[i]}`:`${n} B`}
function ago(t){const s=Date.now()/1000-t;if(s<60)return"just now";if(s<3600)return`${Math.floor(s/60)}m ago`;
  if(s<86400)return`${Math.floor(s/3600)}h ago`;return`${Math.floor(s/86400)}d ago`}
function el(tag,props,...kids){const n=document.createElement(tag);
  for(const[k,v]of Object.entries(props||{})){
    if(k==="class")n.className=v;else if(k==="text")n.textContent=v;
    else if(k==="html")n.innerHTML=v;
    else if(k.startsWith("on"))n.addEventListener(k.slice(2),v);
    else if(v===true)n.setAttribute(k,"");else if(v!==false&&v!=null)n.setAttribute(k,v);}
  for(const kid of kids.flat()){if(kid==null||kid===false)continue;
    n.append(kid instanceof Node?kid:document.createTextNode(String(kid)))}
  return n}
async function api(path,body){const o=body===undefined?{}:{method:"POST",
  headers:{"Content-Type":"application/json"},body:JSON.stringify(body)};
  const r=await fetch(path,o);const d=await r.json().catch(()=>({error:"bad JSON"}));
  if(!r.ok)throw new Error(d.error||("HTTP "+r.status));return d}

/* ------------------------------------------------------------- gallery */
function cardFor(it){
  const sel=state.selected.has(it.path);
  const thumb=el("div",{class:"thumb"});
  if(it.kind==="audio")thumb.append(el("div",{class:"ph",text:"♪"}));
  else thumb.append(el("img",{src:"/thumb/"+encodeURI(it.path),loading:"lazy",alt:it.name,
    onerror:(e)=>{e.target.replaceWith(el("div",{class:"ph",text:it.kind==="video"?"▶":"▢"}))}}));
  const tick=el("input",{type:"checkbox",class:"tick",checked:sel,
    onclick:(e)=>{e.stopPropagation();
      if(e.target.checked)state.selected.add(it.path);else state.selected.delete(it.path);
      updateSel();cardFor_update(e.target.closest(".card"),it.path)}});
  return el("div",{class:"card"+(sel?" sel":""),onclick:()=>openLightbox(it.path)},
    thumb,tick,el("div",{class:"kind",text:it.kind}),
    el("div",{class:"meta"},
      el("div",{class:"nm",text:it.name}),
      el("div",{class:"sub"},el("span",{text:human(it.size)}),el("span",{text:ago(it.mtime)}))));
}
function cardFor_update(card,path){if(card)card.classList.toggle("sel",state.selected.has(path))}
function updateSel(){
  $("zipBtn").disabled=state.selected.size===0;
  $("zipBtn").textContent=state.selected.size?`Download ${state.selected.size} selected`:"Download selected";
}
function renderGrid(append){
  const g=$("grid");
  if(!append)g.textContent="";
  const slice=state.items.slice(append?g.childElementCount:0);
  for(const it of slice)g.append(cardFor(it));
  $("noOut").hidden=state.total>0;
  $("more").hidden=state.items.length>=state.total;
  $("shown").textContent=`showing ${state.items.length} of ${state.total}`;
}
async function loadItems(append){
  if(!append){state.offset=0;state.items=[]}
  const q=new URLSearchParams({offset:state.offset,limit:LIMIT,kind:state.kind,dir:state.dir,q:state.q});
  const d=await api("/api/items?"+q);
  state.items=state.items.concat(d.items);state.total=d.total;state.offset=state.items.length;
  const sel=$("dirFilter");
  if(sel.options.length<=1&&d.dirs.length){
    for(const x of d.dirs)sel.append(el("option",{value:x.dir,text:(x.dir||"(root)")+` (${x.count})`}));
  }
  renderGrid(append);
  $("stats").textContent=`${d.all_total} outputs · ${human(d.bytes_total)}`;
}
function openLightbox(path){
  state.lb=state.items.findIndex(i=>i.path===path);showLightbox();
}
function showLightbox(){
  const it=state.items[state.lb];if(!it)return;
  const stage=$("lbStage");stage.textContent="";
  const url="/media/"+encodeURI(it.path);
  if(it.kind==="image")stage.append(el("img",{src:url,alt:it.name}));
  else if(it.kind==="video")stage.append(el("video",{src:url,controls:true,autoplay:true}));
  else stage.append(el("audio",{src:url,controls:true,autoplay:true}));
  $("lbName").textContent=it.name;
  $("lbMeta").textContent=`${it.dir||"(root)"} · ${human(it.size)} · ${ago(it.mtime)}`;
  $("lbDown").onclick=()=>{location.href="/download/"+encodeURI(it.path)};
  $("lbCopy").onclick=async()=>{try{await navigator.clipboard.writeText(it.path);
    $("lbCopy").textContent="Copied";setTimeout(()=>$("lbCopy").textContent="Copy path",1200)}
    catch{$("lbCopy").textContent="copy failed"}};
  $("lightbox").classList.add("on");
}
function step(d){state.lb=(state.lb+d+state.items.length)%state.items.length;showLightbox()}
$("lbClose").onclick=()=>$("lightbox").classList.remove("on");
$("lbPrev").onclick=(e)=>{e.stopPropagation();step(-1)};
$("lbNext").onclick=(e)=>{e.stopPropagation();step(1)};
document.addEventListener("keydown",(e)=>{
  if(!$("lightbox").classList.contains("on"))return;
  if(e.key==="Escape")$("lightbox").classList.remove("on");
  if(e.key==="ArrowLeft")step(-1);if(e.key==="ArrowRight")step(1)});

$("refresh").onclick=()=>api("/api/items?refresh=1&limit=1").then(()=>loadItems(false));
$("moreBtn").onclick=()=>loadItems(true);
$("selAll").onclick=()=>{state.items.forEach(i=>state.selected.add(i.path));
  $("grid").querySelectorAll(".card").forEach(c=>c.classList.add("sel"));
  $("grid").querySelectorAll(".tick").forEach(t=>t.checked=true);updateSel()};
$("selNone").onclick=()=>{state.selected.clear();
  $("grid").querySelectorAll(".card").forEach(c=>c.classList.remove("sel"));
  $("grid").querySelectorAll(".tick").forEach(t=>t.checked=false);updateSel()};
$("zipBtn").onclick=async()=>{
  $("zipBtn").disabled=true;$("zipBtn").textContent="building zip…";
  try{
    const r=await fetch("/api/zip",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({paths:[...state.selected],name:"comfyui-outputs"})});
    if(!r.ok){throw new Error((await r.json()).error||("HTTP "+r.status))}
    const blob=await r.blob();const a=el("a",{href:URL.createObjectURL(blob),download:"comfyui-outputs.zip"});
    document.body.append(a);a.click();a.remove();
  }catch(err){alert("zip failed: "+err.message)}
  updateSel();
};
document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{
  document.querySelectorAll(".chip").forEach(x=>x.classList.remove("active"));
  c.classList.add("active");state.kind=c.dataset.kind;loadItems(false)});
$("dirFilter").onchange=(e)=>{state.dir=e.target.value;loadItems(false)};
let searchTimer=null;
$("search").oninput=(e)=>{clearTimeout(searchTimer);
  searchTimer=setTimeout(()=>{state.q=e.target.value.trim();loadItems(false)},250)};

/* --------------------------------------------------------------- runner */
let pendingScript=null,pendingName="";
$("tabOut").onclick=()=>{$("viewOut").hidden=false;$("viewRun").hidden=true;
  $("tabOut").classList.add("active");$("tabRun").classList.remove("active")};
$("tabRun").onclick=()=>{$("viewOut").hidden=true;$("viewRun").hidden=false;
  $("tabRun").classList.add("active");$("tabOut").classList.remove("active");loadJobs()};
$("drop").onclick=()=>$("file").click();
$("file").onchange=(e)=>{const f=e.target.files[0];if(f)readScript(f)};
["dragenter","dragover"].forEach(ev=>$("drop").addEventListener(ev,(e)=>{
  e.preventDefault();$("drop").classList.add("hot")}));
["dragleave","drop"].forEach(ev=>$("drop").addEventListener(ev,(e)=>{
  e.preventDefault();$("drop").classList.remove("hot")}));
$("drop").addEventListener("drop",(e)=>{const f=e.dataTransfer.files[0];if(f)readScript(f)});
function readScript(f){
  const r=new FileReader();
  r.onload=()=>{pendingScript=r.result;pendingName=f.name.replace(/\.sh$/,"");
    $("runName").value=pendingName;
    $("runMsg").textContent=`${f.name} loaded (${human(f.size)}) - press Run it`;
    $("runBtn").disabled=false};
  r.readAsText(f);
}
$("paste").oninput=(e)=>{pendingScript=e.target.value;
  $("runBtn").disabled=!pendingScript.trim()};
$("runBtn").onclick=async()=>{
  $("runBtn").disabled=true;$("runMsg").textContent="starting…";
  try{
    const d=await api("/api/run",{name:$("runName").value||pendingName||"preset",
      content:pendingScript,civitai_key:$("civKey").value.trim(),hf_token:$("hfKey").value.trim()});
    $("runMsg").textContent="queued";$("civKey").value="";$("hfKey").value="";
    await loadJobs();selectJob(d.job.id);
  }catch(err){$("runMsg").textContent="failed: "+err.message}
  $("runBtn").disabled=!pendingScript;
};
async function loadJobs(){
  const d=await api("/api/jobs");
  const tb=$("jobs");tb.textContent="";
  $("jobCount").textContent=d.jobs.length;
  $("noJobs").hidden=d.jobs.length>0;
  for(const j of d.jobs){
    const cls=j.status==="ok"?"ok":j.status==="failed"?"bad":
      (j.status==="running"?"run":"queue");
    const took=j.started?( (j.ended||Date.now()/1000)-j.started ):null;
    tb.append(el("tr",{},
      el("td",{},el("a",{href:"#",text:j.name,onclick:(e)=>{e.preventDefault();selectJob(j.id)}})),
      el("td",{},el("span",{class:"badge "+cls,text:j.status})),
      el("td",{class:"hint",text:j.started?new Date(j.started*1000).toLocaleTimeString():"-"}),
      el("td",{class:"hint",text:took!=null?fmtDur(took):"-"}),
      el("td",{class:"hint",text:j.exit_code==null?"-":j.exit_code}),
      el("td",{},el("button",{text:"Log",onclick:()=>selectJob(j.id)}))));
  }
}
function fmtDur(s){s=Math.max(0,Math.round(s));
  return s<60?`${s}s`:`${Math.floor(s/60)}m ${s%60}s`}
async function selectJob(id){
  state.job=id;state.logOffset=0;$("logPanel").hidden=false;$("log").textContent="";
  await pollLog();loadJobs();
}
async function pollLog(){
  if(!state.job)return;
  clearTimeout(state.poll);
  try{
    const d=await api(`/api/job?id=${encodeURIComponent(state.job)}&offset=${state.logOffset}`);
    $("logName").textContent=d.name+" · "+d.status;
    if(d.chunk){const atBottom=$("log").scrollTop+$("log").clientHeight>=$("log").scrollHeight-40;
      $("log").textContent+=d.chunk;state.logOffset=d.offset;
      if(atBottom)$("log").scrollTop=$("log").scrollHeight}
    $("killBtn").hidden=!(d.status==="running"||d.status==="queued");
    if(d.status==="running"||d.status==="queued")state.poll=setTimeout(pollLog,1200);
    else loadJobs();
  }catch(err){$("log").textContent+="\n[panel] "+err.message+"\n"}
}
$("logRefresh").onclick=()=>pollLog();
$("killBtn").onclick=async()=>{if(state.job)await api("/api/job/kill",{id:state.job});pollLog()};

/* ------------------------------------------------------------------ boot */
loadItems(false).catch(e=>{$("stats").textContent="error: "+e.message});
api("/api/health").then(h=>{
  if(!h.runner){$("runBtn").disabled=true;
    $("runMsg").textContent="the runner is disabled on this pod"}
  if(!h.exists)$("stats").textContent="output folder not found: "+h.output_root;
}).catch(()=>{});
</script>
</body>
</html>
"""

LOGIN_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>PodPanel</title>
<style>body{background:#0e1116;color:#e6edf3;font:14px sans-serif;display:grid;place-items:center;
height:100vh;margin:0}form{background:#161b22;border:1px solid #2a323d;border-radius:12px;padding:22px}
input{background:#0b0f14;border:1px solid #2a323d;color:#e6edf3;border-radius:8px;padding:8px 10px}
button{background:#4c8dff;border:0;color:#fff;border-radius:8px;padding:8px 14px;cursor:pointer}</style>
</head><body><form method="get" action="/">
<h3 style="margin:0 0 10px">PodPanel</h3>
<p style="color:#8b98a5;margin:0 0 10px">This panel wants a token.</p>
<input name="token" type="password" placeholder="token" autofocus>
<button>Open</button></form></body></html>"""


# ---------------------------------------------------------------------- main
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="PodPanel - outputs gallery and preset runner.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PODPANEL_PORT", 8090)))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--output", default=os.environ.get("PODPANEL_OUTPUT", OUTPUT_ROOT),
                        help="directory to show in the gallery")
    parser.add_argument("--workdir", default=os.environ.get("PODPANEL_WORKDIR", WORKDIR),
                        help="where uploaded scripts and their logs are kept")
    parser.add_argument("--cwd", default=os.environ.get("PODPANEL_CWD", RUN_CWD),
                        help="working directory a submitted script runs from")
    parser.add_argument("--thumbs", default=os.environ.get("PODPANEL_THUMBS", THUMB_DIR),
                        help="thumbnail cache (put this on local disk, not the volume)")
    parser.add_argument("--token", default=os.environ.get("PODPANEL_TOKEN", ""),
                        help="require ?token=… on every request")
    parser.add_argument("--no-runner", action="store_true",
                        help="disable the drop-in script runner entirely")
    parser.add_argument("--version", action="version", version=f"PodPanel {VERSION}")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    global OUTPUT_ROOT, WORKDIR, THUMB_DIR, TOKEN, RUNNER_ENABLED, RUN_CWD
    args = parse_args(argv)
    OUTPUT_ROOT = os.path.abspath(args.output)
    WORKDIR = os.path.abspath(args.workdir)
    THUMB_DIR = os.path.abspath(args.thumbs)
    RUN_CWD = os.path.abspath(args.cwd)
    TOKEN = args.token or ""
    RUNNER_ENABLED = not args.no_runner

    _detect_tools()
    os.makedirs(THUMB_DIR, exist_ok=True)
    os.makedirs(upload_dir(), exist_ok=True)
    load_history()

    threading.Thread(target=worker_loop, daemon=True).start()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True

    print(f"[podpanel] {VERSION} on http://{args.host}:{args.port}", flush=True)
    print(f"[podpanel] gallery : {OUTPUT_ROOT}"
          f"{'' if os.path.isdir(OUTPUT_ROOT) else '  (does not exist yet)'}", flush=True)
    print(f"[podpanel] runner  : {'off' if not RUNNER_ENABLED else upload_dir()}", flush=True)
    print(f"[podpanel] thumbs  : {THUMB_DIR}  "
          f"(pillow={'yes' if PIL else 'no'}, ffmpeg={'yes' if FFMPEG else 'no'})", flush=True)
    if TOKEN:
        print("[podpanel] a token is required", flush=True)

    def stop(_signum, _frame):
        print("[podpanel] shutting down", flush=True)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, stop)
        except (ValueError, OSError):
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
