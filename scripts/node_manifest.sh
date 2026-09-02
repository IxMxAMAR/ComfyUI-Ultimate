#!/usr/bin/env bash
# Custom-node manifest handling for ComfyUI-Ultimate-ST.
#
# The problem this solves: ComfyUI, its venv and the 29 baked node packs live in
# the image on local NVMe, which is why this image boots much faster than
# templates that install onto the network volume. The cost of that choice is
# that anything ComfyUI-Manager installs at runtime dies with the pod.
#
# The fix is a manifest, not a symlink. /workspace/comfy_nodes.txt lists the
# nodes you want; at boot they are cloned back onto LOCAL disk and their
# requirements reinstalled. Node code therefore still imports at local-disk
# speed, and the list is portable across pods, volumes and accounts.
#
# Manifest format is identical to the image's own node_pins.txt:
#     <dirname> <git_url> <commit_sha>
# with two conveniences: the sha may be omitted (tracks the default branch), and
# a bare URL infers its own dirname.
#
# Sourced by restore_nodes.sh and by the comfy-nodes CLI; kept side-effect free
# at source time so tests/test_nodes.sh can exercise it directly.

# Where ComfyUI keeps node packs (local disk, deliberately not the volume).
COMFY_NODES_DIR="${COMFY_NODES_DIR:-/ComfyUI/custom_nodes}"
# The 29 packs baked into the image; these must never be touched by the manifest.
CN_BAKED_LIST="${CN_BAKED_LIST:-/opt/expected_packs.txt}"

cn_manifest_path() {
  echo "${WORKSPACE:-/workspace}/comfy_nodes.txt"
}

cn_log_path() {
  echo "${WORKSPACE:-/workspace}/comfy_nodes.log"
}

# github.com/foo/Bar-Nodes(.git)(/) -> Bar-Nodes
cn_dirname_from_url() {
  local url="$1"
  url="${url%/}"
  url="${url%.git}"
  echo "${url##*/}"
}

# Emit one normalised "<dirname> <url> <sha>" per entry, skipping comments and
# blanks. Accepts 3-field, 2-field (sha defaults to HEAD) and bare-URL lines.
cn_parse() {
  local file="${1:-$(cn_manifest_path)}"
  [ -f "$file" ] || return 0
  while read -r a b c _rest; do
    case "$a" in ''|'#'*) continue ;; esac
    if [ -z "$b" ]; then
      # bare URL
      echo "$(cn_dirname_from_url "$a") $a HEAD"
    elif [ -z "$c" ]; then
      echo "$a $b HEAD"
    else
      echo "$a $b $c"
    fi
  done < "$file"
}

# True when the directory name belongs to a pack baked into the image.
cn_is_baked() {
  local name="$1"
  [ -f "$CN_BAKED_LIST" ] || return 1
  grep -qxF "$name" "$CN_BAKED_LIST"
}

# ComfyUI-Manager installs from the Comfy Registry as a versioned archive, not a
# git clone, so those packs have NO .git directory. Freezing only git checkouts
# would silently drop them and lose them on the next rebuild. The Registry does
# mandate a Repository url in pyproject.toml, so use that as the fallback.
cn_repo_url_from_pyproject() {
  local f="$1/pyproject.toml"
  [ -f "$f" ] || return 1
  sed -n 's/^[[:space:]]*Repository[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$f" | head -1
}

# True when $1 is a node directory this user added (not baked into the image).
_cn_is_user_dir() {
  local name="$1"
  [ "$name" != "*" ] || return 1
  ! cn_is_baked "$name"
}

# Scan the installed node dirs and emit manifest lines for everything the user
# added themselves. A real git checkout is pinned to the exact commit it is
# running; a Registry install can only be tracked at HEAD, since the archive
# carries no commit id.
cn_freeze_lines() {
  local d name url sha
  [ -d "$COMFY_NODES_DIR" ] || return 0
  for d in "$COMFY_NODES_DIR"/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    _cn_is_user_dir "$name" || continue

    if [ -d "$d/.git" ]; then
      url="$(git -C "$d" config --get remote.origin.url 2>/dev/null)"
      sha="$(git -C "$d" rev-parse HEAD 2>/dev/null)"
      if [ -n "$url" ] && [ -n "$sha" ]; then
        echo "$name $url $sha"
        continue
      fi
    fi

    url="$(cn_repo_url_from_pyproject "$d" 2>/dev/null)"
    [ -n "$url" ] || continue
    echo "$name $url HEAD"
  done
}

# Node dirs the user added that cannot be recorded at all — no git remote and no
# Repository url. These WILL be lost on a rebuild, so they must be reported
# rather than silently skipped.
cn_unrecordable_dirs() {
  local d name recorded
  [ -d "$COMFY_NODES_DIR" ] || return 0
  recorded="$(cn_freeze_lines | awk '{print $1}')"
  for d in "$COMFY_NODES_DIR"/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    _cn_is_user_dir "$name" || continue
    echo "$recorded" | grep -qxF "$name" && continue
    echo "$name"
  done
}
