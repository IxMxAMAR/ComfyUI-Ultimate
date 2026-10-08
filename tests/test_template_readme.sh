#!/usr/bin/env bash
# The RunPod template page README, and the tool that pushes it.
#
# Entirely offline: it reads the markdown, reads the tool's source, and checks the
# tool's behaviour without a key. Nothing here talks to RunPod -- the push itself is
# verified by hand against a throwaway template, because it needs a real key.
set -u
cd "$(dirname "$0")" || exit 1
. ./helpers.sh

README="../docs/template-readme.md"
TOOL="../tools/set_template_readme.py"
PY="$(command -v python3 || command -v python)"

assert_file "$README" "the template README exists"
assert_file "$TOOL" "the readme push tool exists"

if [ ! -f "$README" ]; then
  echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
  exit 0
fi

body="$(cat "$README")"

# --- the facts the page must state -----------------------------------------
for needle in \
  "ixmxamar/comfyui-ultimate:latest" \
  "/workspace" \
  "SageAttention" \
  "FlashAttention" \
  "29" \
  "CIVITAI_API_KEY" \
  "HF_TOKEN" \
  "PODPANEL_TOKEN" \
  "PODPANEL_ENABLE" \
  "JUPYTER_TOKEN" \
  "COMFY_ARGS" \
  "Network Volume" \
  "github.com/IxMxAMAR/ComfyUI-Ultimate"
do
  TESTS_RUN=$((TESTS_RUN + 1))
  case "$body" in
    *"$needle"*) echo "  ok: the README mentions $needle" ;;
    *) fail "the README never mentions $needle" ;;
  esac
done

# --- every service, on the port it really uses ------------------------------
for port in 8188 8888 8080 8090 22; do
  TESTS_RUN=$((TESTS_RUN + 1))
  case "$body" in
    *"$port"*) echo "  ok: the README documents port $port" ;;
    *) fail "the README does not document port $port" ;;
  esac
done

# --- the console's editor is the real constraint, not the API ---------------
# RunPod's console stops at 5000 characters. The API itself took 20,000 in a probe,
# but anything past the console limit cannot be edited on the page afterwards, so the
# file has to stay inside it.
TESTS_RUN=$((TESTS_RUN + 1))
if [ -n "$PY" ]; then
  chars="$("$PY" -c 'import sys;print(len(open(sys.argv[1],encoding="utf-8").read().rstrip()))' "$README")"
else
  chars="$(printf '%s' "$body" | wc -c | tr -d ' ')"   # bytes: the stricter reading
fi
if [ "$chars" -le 5000 ]; then
  echo "  ok: the README is $chars chars, inside the console's 5000 limit"
else
  fail "the README is $chars chars, over the console's 5000 limit"
fi

# --- the 403 advice must stay correct --------------------------------------
# The old text told people to use Incognito or a hard refresh, and blamed a cached
# 403. That is wrong: the 403 is ComfyUI's CSRF middleware rejecting a cross-site
# navigation, and the image patches it. Naming the remedies in order to debunk them
# is fine, so match the prescriptive wording, not the bare words.
TESTS_RUN=$((TESTS_RUN + 1))
bad=""
for phrase in "Ctrl+Shift+R" "Incognito window" "incognito window" "cached 403"; do
  case "$body" in *"$phrase"*) bad="$bad [$phrase]" ;; esac
done
if [ -n "$bad" ]; then
  fail "the README repeats the debunked 403 remedy:$bad"
else
  echo "  ok: the README does not repeat the debunked 403 remedy"
fi

TESTS_RUN=$((TESTS_RUN + 1))
case "$body" in
  *CSRF*) echo "  ok: the README explains the 403 as ComfyUI's CSRF middleware" ;;
  *) fail "the README does not explain the 403 as CSRF" ;;
esac

# --- the README and the tool must agree on the ports ------------------------
if [ -f "$TOOL" ]; then
  tool_ports="$(sed -n 's/^DOCUMENTED_PORTS = \[\(.*\)\]$/\1/p' "$TOOL" | tr -d ' "' | tr ',' '\n' | sed 's#/.*##' | grep -v '^$')"
  for port in $tool_ports; do
    TESTS_RUN=$((TESTS_RUN + 1))
    case "$body" in
      *"$port"*) echo "  ok: the tool's port $port is documented in the README" ;;
      *) fail "the tool lists port $port but the README does not document it" ;;
    esac
  done
fi

# --- the tool itself -------------------------------------------------------
if [ -z "$PY" ]; then
  skip "no python3 to exercise tools/set_template_readme.py"
else
  assert_true "the tool compiles" "$PY" -m py_compile "$TOOL"
  assert_true "the tool has a --help" "$PY" "$TOOL" --help

  # No key anywhere: it must say how to get one, not traceback.
  tmp_home="$(mktemp -d)"
  out="$(env -u RUNPOD_API_KEY HOME="$tmp_home" USERPROFILE="$tmp_home" \
         "$PY" "$TOOL" --show 2>&1)"
  rc=$?
  rm -rf "$tmp_home"
  assert_eq "$([ "$rc" -ne 0 ] && echo yes || echo no)" "yes" \
    "with no key the tool exits non-zero"
  TESTS_RUN=$((TESTS_RUN + 1))
  case "$out" in
    *"No API key"*) echo "  ok: with no key the tool explains where to get one" ;;
    *) fail "with no key the tool did not explain itself — got: $out" ;;
  esac

  # A missing readme file must be reported, not silently pushed as nothing.
  out="$("$PY" "$TOOL" --readme /nonexistent/readme.md --key dummy 2>&1)"
  TESTS_RUN=$((TESTS_RUN + 1))
  case "$out" in
    *"No such readme file"*) echo "  ok: a missing readme file is reported" ;;
    *) fail "a missing readme file was not reported — got: $out" ;;
  esac
fi

# --- no secret may be committed -------------------------------------------
TESTS_RUN=$((TESTS_RUN + 1))
if grep -rqE 'apikey[[:space:]]*=[[:space:]]*"[A-Za-z0-9]{20,}"' "$TOOL" "$README" 2>/dev/null; then
  fail "an API key appears to be committed in the tool or the README"
else
  echo "  ok: no API key is committed"
fi

echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
