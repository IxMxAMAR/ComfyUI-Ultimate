#!/usr/bin/env bash
# shellcheck source=helpers.sh
. "$(dirname "$0")/helpers.sh"
. "$(dirname "$0")/../scripts/node_manifest.sh"

new_node_sandbox() {
  new_sandbox
  export COMFY_NODES_DIR="$SANDBOX/custom_nodes"
  export CN_BAKED_LIST="$SANDBOX/expected_packs.txt"
  mkdir -p "$COMFY_NODES_DIR"
  printf 'ComfyUI-Manager\nrgthree-comfy\n' > "$CN_BAKED_LIST"
}

# Builds a fake installed node that looks like a real git checkout.
fake_node_repo() {
  local name="$1" url="$2"
  local d="$COMFY_NODES_DIR/$name"
  mkdir -p "$d"
  git -C "$d" init -q 2>/dev/null
  git -C "$d" config user.email t@t.t; git -C "$d" config user.name t
  git -C "$d" remote add origin "$url" 2>/dev/null
  echo x > "$d/f.txt"; git -C "$d" add -A; git -C "$d" commit -qm x
  git -C "$d" rev-parse HEAD
}

echo "-- cn_dirname_from_url"
new_node_sandbox
assert_eq "$(cn_dirname_from_url https://github.com/foo/Bar-Nodes.git)" "Bar-Nodes" "strips .git"
assert_eq "$(cn_dirname_from_url https://github.com/foo/Bar-Nodes)"     "Bar-Nodes" "handles no .git"
assert_eq "$(cn_dirname_from_url https://github.com/foo/Bar-Nodes/)"    "Bar-Nodes" "handles trailing slash"
cleanup_sandbox

echo "-- cn_parse normalises the manifest"
new_node_sandbox
cat > "$WORKSPACE/comfy_nodes.txt" <<'EOF'
# a comment

MyNode https://github.com/foo/MyNode.git abc123
OtherNode https://github.com/foo/OtherNode.git
https://github.com/foo/Shorthand.git
EOF
out="$(cn_parse "$WORKSPACE/comfy_nodes.txt")"
assert_eq "$(echo "$out" | wc -l | tr -d ' ')" "3" "comments and blanks are skipped"
assert_eq "$(echo "$out" | sed -n 1p)" "MyNode https://github.com/foo/MyNode.git abc123" "three-field line kept as-is"
assert_eq "$(echo "$out" | sed -n 2p)" "OtherNode https://github.com/foo/OtherNode.git HEAD" "missing sha defaults to HEAD"
assert_eq "$(echo "$out" | sed -n 3p)" "Shorthand https://github.com/foo/Shorthand.git HEAD" "bare url infers the dirname"
cleanup_sandbox

echo "-- cn_is_baked protects the image's own node packs"
new_node_sandbox
assert_true  "a baked pack is recognised"     cn_is_baked ComfyUI-Manager
assert_true  "another baked pack"             cn_is_baked rgthree-comfy
assert_true  "a user node is not baked" bash -c '. "'"$(dirname "$0")"'/../scripts/node_manifest.sh"; ! cn_is_baked MyRandomNode'
cleanup_sandbox

echo "-- cn_freeze_lines captures user nodes only, at their exact commit"
new_node_sandbox
sha_user="$(fake_node_repo MyNode https://github.com/foo/MyNode.git)"
fake_node_repo ComfyUI-Manager https://github.com/ltdrdata/ComfyUI-Manager.git >/dev/null
mkdir -p "$COMFY_NODES_DIR/not-a-repo"
out="$(cn_freeze_lines)"
assert_eq "$(echo "$out" | wc -l | tr -d ' ')" "1" "only the non-baked git checkout is captured"
assert_eq "$out" "MyNode https://github.com/foo/MyNode.git $sha_user" "captured with url and exact sha"
cleanup_sandbox

echo "SUITE_RESULT $TESTS_RUN $TESTS_FAILED $TESTS_SKIPPED"
