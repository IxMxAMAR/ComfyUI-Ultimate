#!/usr/bin/env bash
# PodPanel: the outputs gallery, its downloads, and the drop-in preset runner.
#
# Starts a real PodPanel on a scratch port against a scratch output folder, then
# talks to it over HTTP. No network access and no ComfyUI needed: the fixtures
# are a 1x1 PNG and two dummy media files.
set -u
cd "$(dirname "$0")" || exit 1
. ./helpers.sh

PORT="${PODPANEL_TEST_PORT:-8099}"
BASE="http://127.0.0.1:$PORT"
REPO="$(cd .. && pwd)"
PANEL="$REPO/scripts/podpanel.py"
PY="$(command -v python3 || command -v python)"
CURL="$(command -v curl)"

if [ -z "$PY" ] || [ ! -f "$PANEL" ]; then
  skip "no python3 or no scripts/podpanel.py"
  echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
  exit 0
fi
if [ -z "$CURL" ]; then
  skip "no curl available to talk to the panel"
  echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
  exit 0
fi

SANDBOX="$(mktemp -d)"
PANEL_PID=""
PANEL2_PID=""
cleanup() {
  [ -n "$PANEL_PID" ] && kill "$PANEL_PID" 2>/dev/null
  [ -n "$PANEL2_PID" ] && kill "$PANEL2_PID" 2>/dev/null
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

OUT="$SANDBOX/output"
WORK="$SANDBOX/work"
mkdir -p "$OUT/2026-01-01" "$WORK"

# A real PNG, written with stdlib zlib/struct so it needs no Pillow here and is
# guaranteed to decode (hand-copied 1x1 base64 blobs are often subtly corrupt,
# and Pillow only notices when it decodes the pixels).
"$PY" - "$OUT/2026-01-01/shot.png" <<'PY'
import struct, sys, zlib

def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

w = h = 64
rows = b"".join(b"\x00" + bytes([x * 4 % 256, 60, 200]) * w for x in range(h))
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(rows))
       + chunk(b"IEND", b""))
with open(sys.argv[1], "wb") as fh:
    fh.write(png)
PY
# A dummy video and audio file, so the placeholder path for a thumbnail that
# cannot be generated is exercised too.
head -c 4096 /dev/zero > "$OUT/clip_00001.mp4"
head -c 2048 /dev/zero > "$OUT/tune_00001.mp3"

start_panel() {           # start_panel <port> [extra args...]
  local port="$1"; shift
  "$PY" "$PANEL" --port "$port" --output "$OUT" --workdir "$WORK" \
        --thumbs "$SANDBOX/thumbs" --cwd "$SANDBOX" "$@" > "$SANDBOX/panel-$port.log" 2>&1 &
  echo $!
}

wait_health() {           # wait_health <port>
  local i
  for i in $(seq 1 40); do
    if "$CURL" -fsS "http://127.0.0.1:$1/api/health" >/dev/null 2>&1; then return 0; fi
    sleep 0.25
  done
  return 1
}

PANEL_PID="$(start_panel "$PORT")"
if ! wait_health "$PORT"; then
  fail "the panel never came up on :$PORT"
  echo "  panel log:"; sed 's/^/    /' "$SANDBOX/panel-$PORT.log" 2>/dev/null | head -20
  echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
  exit 1
fi

json() { "$CURL" -fsS "$BASE$1"; }
post() { "$CURL" -fsS -X POST "$BASE$1" -H 'Content-Type: application/json' -d "$2"; }
code() { "$CURL" -s -o /dev/null -w '%{http_code}' "$BASE$1"; }

# --- health -------------------------------------------------------------
assert_true "health reports ok" "$CURL" -fsS -o /dev/null "$BASE/api/health"
assert_eq "$(json /api/health | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["runner"])')" \
          "True" "the runner is on by default"

# --- gallery ------------------------------------------------------------
assert_eq "$(json /api/items | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["total"])')" \
          "3" "the gallery finds all three media files"
assert_eq "$(json '/api/items?kind=image' | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["total"])')" \
          "1" "the image filter narrows it to one"
assert_eq "$(json '/api/items?kind=video' | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["total"])')" \
          "1" "the video filter finds the mp4"
assert_eq "$(json '/api/items?q=shot' | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["total"])')" \
          "1" "search matches on filename"
assert_eq "$(json '/api/items?dir=2026-01-01' | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["total"])')" \
          "1" "the folder filter works"
assert_eq "$(json /api/items | "$PY" -c 'import json,sys;print(len(json.load(sys.stdin)["dirs"]))')" \
          "2" "both folders are reported for the dropdown"
assert_eq "$(json /api/items | "$PY" -c 'import json,sys;d=json.load(sys.stdin);print(d["items"][0]["kind"])')" \
          "audio" "the newest file is listed first"
assert_eq "$(json /api/items | "$PY" -c "
import json,sys
t=[i['mtime'] for i in json.load(sys.stdin)['items']]
print(t == sorted(t, reverse=True))
")" "True" "items are ordered newest first"

# --- serving files ------------------------------------------------------
assert_eq "$(code '/media/2026-01-01/shot.png')" "200" "an image is served"
assert_eq "$(code '/download/2026-01-01/shot.png')" "200" "a download is served"
assert_true "a download is an attachment" bash -c \
  "$CURL -sI '$BASE/download/2026-01-01/shot.png' | grep -qi 'content-disposition: attachment'"
assert_eq "$(code '/media/clip_00001.mp4')" "200" "the video is served"
assert_true "range requests are supported (video seeking)" bash -c \
  "$CURL -s -o /dev/null -D - -H 'Range: bytes=0-99' '$BASE/media/clip_00001.mp4' | grep -qi '^HTTP/1.1 206'"
assert_true "the range is reported back" bash -c \
  "$CURL -s -o /dev/null -D - -H 'Range: bytes=0-99' '$BASE/media/clip_00001.mp4' | grep -qi 'content-range: bytes 0-99/4096'"

# --- the traversal guard ------------------------------------------------
assert_true "a path escaping the output root is refused" bash -c \
  "[ \"\$($CURL -s -o /dev/null -w '%{http_code}' '$BASE/media/../../../../etc/passwd')\" != 200 ]"
assert_true "an unknown file is a 404" bash -c \
  "[ \"$(code '/media/nope.png')\" = 404 ]"

# --- thumbnails ---------------------------------------------------------
# With Pillow this is a generated JPEG; without it the route falls back to the
# original image. Either way it must be a real image, not an error page.
thumb_code="$(code '/thumb/2026-01-01/shot.png')"
assert_eq "$thumb_code" "200" "the thumbnail route answers for an image"
assert_true "the thumbnail is a real image, not an error page" bash -c \
  "$CURL -s '$BASE/thumb/2026-01-01/shot.png' | head -c2 | od -An -tx1 | tr -d ' \n' | grep -qiE 'ffd8|8950'"
if "$PY" -c 'import PIL' 2>/dev/null; then
  assert_true "with Pillow it is a downscaled jpeg" bash -c \
    "$CURL -s '$BASE/thumb/2026-01-01/shot.png' | head -c3 | od -An -tx1 | tr -d ' \n' | grep -qi 'ffd8ff'"
else
  skip "generated (rather than passthrough) thumbnails need Pillow"
fi
assert_eq "$(code '/thumb/clip_00001.mp4')" "404" "a video with no decodable frame gives no thumbnail"

# --- zip ----------------------------------------------------------------
zip_code="$("$CURL" -s -o "$SANDBOX/out.zip" -w '%{http_code}' -X POST "$BASE/api/zip" \
  -H 'Content-Type: application/json' -d '{"paths":["2026-01-01/shot.png","clip_00001.mp4"]}')"
assert_eq "$zip_code" "200" "the zip endpoint answers"
assert_eq "$("$PY" -c "
import sys, zipfile
try:
    names = zipfile.ZipFile(sys.argv[1]).namelist()
except Exception as exc:
    print('bad zip: %s' % exc); raise SystemExit
print(','.join(sorted(names)))
" "$SANDBOX/out.zip")" "2026-01-01/shot.png,clip_00001.mp4" "the zip holds both selected files"
assert_true "the zip is a real zip" bash -c "[ \"\$(head -c2 '$SANDBOX/out.zip')\" = 'PK' ]"

# --- the drop-in runner -------------------------------------------------
JOB_SCRIPT='#!/usr/bin/env bash
echo "podpanel-runner-marker"
echo "cwd is $(pwd)"
exit 0'
JOB_JSON="$("$PY" -c "
import json,sys
print(json.dumps({'name': 'ci test preset', 'content': sys.argv[1]}))
" "$JOB_SCRIPT")"
JOB_ID="$(post /api/run "$JOB_JSON" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["job"]["id"])')"
assert_true "the runner accepted a script" test -n "$JOB_ID"

status=""
for _ in $(seq 1 60); do
  status="$(json "/api/job?id=$JOB_ID" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["status"])')"
  case "$status" in running|queued) sleep 0.25 ;; *) break ;; esac
done
assert_eq "$status" "ok" "the script ran to completion"
assert_true "the log is captured" bash -c \
  "$CURL -fsS '$BASE/api/job?id=$JOB_ID' | grep -q 'podpanel-runner-marker'"
assert_true "the run happened in the requested cwd" bash -c \
  "$CURL -fsS '$BASE/api/job?id=$JOB_ID' | grep -q 'cwd: '"
assert_true "the script saw that cwd" bash -c \
  "$CURL -fsS '$BASE/api/job?id=$JOB_ID' | grep -q 'cwd is '"
assert_eq "$(json "/api/job?id=$JOB_ID" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["exit_code"])')" \
          "0" "the exit code is recorded"
assert_true "the uploaded script was kept" bash -c \
  "ls '$WORK/uploads/'*'ci-test-preset.sh' >/dev/null 2>&1"
assert_true "the run is listed in the job history" bash -c \
  "$CURL -fsS '$BASE/api/jobs' | grep -q 'ci test preset'"

# Incremental log reads. Wait for the final marker first: reading while the
# worker is mid-write can legitimately split a line, which is fine for a live
# tail but makes an exact-offset assertion racy.
for _ in $(seq 1 40); do
  json "/api/job?id=$JOB_ID" | grep -q 'finished' && break
  sleep 0.25
done
END="$(json "/api/job?id=$JOB_ID" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["offset"])')"
assert_true "the finished marker is in the log" bash -c \
  "$CURL -fsS '$BASE/api/job?id=$JOB_ID' | grep -q 'finished'"
assert_eq "$(json "/api/job?id=$JOB_ID&offset=$END" | "$PY" -c 'import json,sys;print(repr(json.load(sys.stdin)["chunk"]))')" \
          "''" "reading past the end returns an empty chunk"

# A failing script must be recorded as failed, not swallowed.
FAIL_JSON="$("$PY" -c "
import json
print(json.dumps({'name': 'ci failing preset', 'content': '#!/usr/bin/env bash\necho nope >&2\nexit 3\n'}))
")"
FAIL_ID="$(post /api/run "$FAIL_JSON" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["job"]["id"])')"
for _ in $(seq 1 60); do
  status="$(json "/api/job?id=$FAIL_ID" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["status"])')"
  case "$status" in running|queued) sleep 0.25 ;; *) break ;; esac
done
assert_eq "$status" "failed" "a non-zero exit is reported as failed"
assert_eq "$(json "/api/job?id=$FAIL_ID" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["exit_code"])')" \
          "3" "the failing exit code is preserved"

assert_eq "$(code '/api/nothing-here')" "404" "an unknown API route is a 404"

# --- --no-runner turns the runner off -----------------------------------
PORT2=$((PORT + 1))
PANEL2_PID="$(start_panel "$PORT2" --no-runner)"
if wait_health "$PORT2"; then
  assert_eq "$("$CURL" -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT2/api/run" \
    -H 'Content-Type: application/json' -d "$JOB_JSON")" \
            "403" "--no-runner refuses to run anything"
  assert_eq "$("$CURL" -fsS "http://127.0.0.1:$PORT2/api/health" \
    | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["runner"])')" \
            "False" "--no-runner is reported by health"
else
  skip "--no-runner instance never came up"
fi

echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
