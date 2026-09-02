#!/usr/bin/env bash
# Minimal assertion helpers. No external test framework: the only guaranteed
# runtime on both the dev box (Git Bash) and CI (ubuntu-latest) is bash itself.

TESTS_RUN=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Git Bash on Windows cannot create real symlinks without Developer Mode; it
# silently copies the directory instead. Symlink behaviour is therefore only
# assertable on Linux — which is where CI runs and where the image actually
# executes, so the assertions below are still enforced where it counts.
_SYMLINKS_OK=""
symlinks_supported() {
  if [ -z "$_SYMLINKS_OK" ]; then
    local d
    d="$(mktemp -d)"
    mkdir -p "$d/t"
    if ln -sfn "$d/t" "$d/l" 2>/dev/null && [ -L "$d/l" ]; then
      _SYMLINKS_OK=yes
    else
      _SYMLINKS_OK=no
    fi
    rm -rf "$d"
  fi
  [ "$_SYMLINKS_OK" = "yes" ]
}

skip() {
  TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
  echo "  SKIP: $1"
}

fail() {
  TESTS_FAILED=$((TESTS_FAILED + 1))
  echo "  FAIL: $1" >&2
}

assert_eq() {
  local actual="$1" expected="$2" label="$3"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$actual" = "$expected" ]; then
    echo "  ok: $label"
  else
    fail "$label — expected [$expected], got [$actual]"
  fi
}

assert_true() {
  local label="$1"; shift
  TESTS_RUN=$((TESTS_RUN + 1))
  if "$@"; then
    echo "  ok: $label"
  else
    fail "$label — command failed: $*"
  fi
}

assert_file() {
  local path="$1" label="$2"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ -f "$path" ]; then
    echo "  ok: $label"
  else
    fail "$label — no such file: $path"
  fi
}

assert_symlink_to() {
  local link="$1" target="$2" label="$3"
  if ! symlinks_supported; then
    skip "$label (no symlink support on this platform; enforced in CI on Linux)"
    return 0
  fi
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$target" ]; then
    echo "  ok: $label"
  else
    fail "$label — $link is not a symlink to $target (got: $(readlink "$link" 2>/dev/null || echo 'not a symlink'))"
  fi
}

# Builds an isolated fake filesystem: a fake SillyTavern app dir and a fake
# empty volume. Sets ST_APP and WORKSPACE to point at them.
new_sandbox() {
  SANDBOX="$(mktemp -d)"
  export ST_APP="$SANDBOX/SillyTavern"
  export WORKSPACE="$SANDBOX/workspace"
  mkdir -p "$ST_APP/public/scripts/extensions/third-party" "$WORKSPACE"
  unset ST_USER ST_PASSWORD ST_DISABLE
}

cleanup_sandbox() {
  [ -n "${SANDBOX:-}" ] && rm -rf "$SANDBOX"
}
