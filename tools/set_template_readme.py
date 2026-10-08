#!/usr/bin/env python3
"""Push docs/template-readme.md to the RunPod template page, or create the template.

The template's README is not part of the image and not part of this repo as far as
RunPod is concerned: it lives on the template record and is served by the GraphQL API.
REST v2 cannot set it -- its UpdateTemplateRequest rejects unknown properties
(``unevaluatedProperties: false``) and has no ``readme`` field at all.

So this talks to https://api.runpod.io/graphql and calls ``saveTemplate``, which is an
upsert: it needs the template's whole container definition, not just the readme. The
existing definition is read first and echoed back unchanged, except for the readme and
(unless --no-add-port) the PodPanel port.

    python tools/set_template_readme.py --dry-run        # show what would change
    python tools/set_template_readme.py                  # push it
    python tools/set_template_readme.py --show           # print the live readme
    python tools/set_template_readme.py --create         # make the template

The key is read from --key, then $RUNPOD_API_KEY, then ~/.runpod/config.toml. It must
belong to the account that owns the template; a key for another account can read a
public template but every write returns "template not found".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

GRAPHQL = "https://api.runpod.io/graphql"
USER_AGENT = "comfyui-ultimate-template-readme/1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_README = os.path.join(ROOT, "docs", "template-readme.md")
DEFAULT_TEMPLATE = "lbw5xj63wp"

# Ports the README documents. PodPanel (8090) is the one most easily left out of a
# template made before it existed.
DOCUMENTED_PORTS = ["8188/http", "8888/http", "8080/http", "8090/http", "22/tcp", "22/udp"]
PODPANEL_PORT = "8090/http"

TEMPLATE_QUERY = """
query($id: String!) {
  podTemplate(id: $id) {
    id name imageName dockerArgs containerDiskInGb volumeInGb volumeMountPath
    ports env { key value } readme isPublic isServerless category
    startSsh startJupyter allowedCudaVersions
  }
}
"""

SAVE_MUTATION = """
mutation($input: SaveTemplateInput!) {
  saveTemplate(input: $input) { id name readme }
}
"""

# What --create builds, matching the published template.
CANONICAL = {
    "name": "ComfyUI Ultimate",
    "imageName": "ixmxamar/comfyui-ultimate:latest",
    "dockerArgs": "",
    "containerDiskInGb": 25,
    "volumeInGb": 150,
    "volumeMountPath": "/workspace",
    "ports": ",".join(DOCUMENTED_PORTS),
    "env": [],
    "isPublic": True,
    "isServerless": False,
    "category": "NVIDIA",
    "startSsh": True,
    "startJupyter": True,
}

# Only these go back into SaveTemplateInput; anything else the query returns is
# read-only and would be rejected.
WRITABLE = [
    "id", "name", "imageName", "dockerArgs", "containerDiskInGb", "volumeInGb",
    "volumeMountPath", "ports", "env", "readme", "isPublic", "isServerless",
    "category", "startSsh", "startJupyter", "allowedCudaVersions",
]


class ApiError(RuntimeError):
    pass


def find_key(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    from_env = os.environ.get("RUNPOD_API_KEY", "").strip()
    if from_env:
        return from_env
    config = os.path.join(os.path.expanduser("~"), ".runpod", "config.toml")
    if os.path.exists(config):
        with open(config, encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("apikey"):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    raise SystemExit(
        "No API key. Pass --key, set RUNPOD_API_KEY, or run `flash login`.\n"
        "Get one at https://console.runpod.io/user/settings"
    )


def gql(key: str, query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(GRAPHQL, data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            out = json.loads(raw)
        except ValueError:
            raise ApiError(f"HTTP {exc.code} from RunPod: {raw[:300]}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"Could not reach RunPod: {exc.reason}") from exc

    if out.get("errors"):
        message = "; ".join(e.get("message", "?") for e in out["errors"])
        raise ApiError(message)
    return out.get("data") or {}


def fetch_template(key: str, template_id: str) -> dict | None:
    data = gql(key, TEMPLATE_QUERY, {"id": template_id})
    return data.get("podTemplate")


def save_template(key: str, payload: dict) -> dict:
    data = gql(key, SAVE_MUTATION, {"input": payload})
    saved = data.get("saveTemplate")
    if not saved:
        raise ApiError("RunPod accepted the request but returned no template.")
    return saved


def build_payload(current: dict, readme: str, add_port: bool) -> tuple[dict, list[str]]:
    """Echo the live definition back, changing only the readme and the ports."""
    payload = {field: current.get(field) for field in WRITABLE if field in current}
    notes: list[str] = []

    # Required by SaveTemplateInput even when unchanged.
    payload.setdefault("name", CANONICAL["name"])
    payload.setdefault("dockerArgs", "")
    payload.setdefault("containerDiskInGb", CANONICAL["containerDiskInGb"])
    payload.setdefault("volumeInGb", CANONICAL["volumeInGb"])
    payload.setdefault("env", [])

    before = [p.strip() for p in (current.get("ports") or "").split(",") if p.strip()]
    if add_port and PODPANEL_PORT not in before:
        after = list(before)
        # Keep the documented order where it can be, append otherwise.
        ordered = [p for p in DOCUMENTED_PORTS if p in after or p == PODPANEL_PORT]
        extra = [p for p in after if p not in ordered]
        payload["ports"] = ",".join(ordered + extra)
        notes.append(f"ports: adding {PODPANEL_PORT}")
    else:
        payload["ports"] = ",".join(before) if before else CANONICAL["ports"]

    payload["readme"] = readme
    if (current.get("readme") or "") != readme:
        notes.append(f"readme: {len(current.get('readme') or '')} -> {len(readme)} chars")
    return payload, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--template", default=DEFAULT_TEMPLATE,
                        help=f"template id (default {DEFAULT_TEMPLATE})")
    parser.add_argument("--readme", default=DEFAULT_README, help="markdown file to push")
    parser.add_argument("--key", help="RunPod API key (else $RUNPOD_API_KEY, else config.toml)")
    parser.add_argument("--show", action="store_true", help="print the live readme and exit")
    parser.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    parser.add_argument("--no-add-port", action="store_true",
                        help=f"do not add {PODPANEL_PORT} to the template's ports")
    parser.add_argument("--create", action="store_true",
                        help="create the template instead of updating one")
    args = parser.parse_args()

    key = find_key(args.key)

    def missing_template() -> int:
        print(f"Template {args.template} was not found for this account.", file=sys.stderr)
        print("A key for a different account can read a public template but cannot write it;\n"
              "use the key belonging to the account that owns it.", file=sys.stderr)
        return 2

    if args.show:
        # Read-only, so no readme file is needed.
        current = fetch_template(key, args.template)
        if current is None:
            return missing_template()
        print(current.get("readme") or "(this template has no readme)")
        return 0

    # Check the local input before making any network call.
    if not os.path.exists(args.readme):
        print(f"No such readme file: {args.readme}", file=sys.stderr)
        return 2
    with open(args.readme, encoding="utf-8") as fh:
        readme = fh.read()

    if args.create:
        current = dict(CANONICAL)
        current["id"] = None
    else:
        current = fetch_template(key, args.template)
        if current is None:
            return missing_template()

    if args.create:
        payload = dict(CANONICAL)
        payload["readme"] = readme
        notes = [f"creating a new template named {CANONICAL['name']!r}"]
    else:
        payload, notes = build_payload(current, readme, add_port=not args.no_add_port)

    print(f"template : {current.get('id') or '(new)'}  {current.get('name', '')}")
    print(f"image    : {current.get('imageName', CANONICAL['imageName'])}")
    for note in notes or ["no changes needed"]:
        print(f"  - {note}")

    if args.dry_run:
        print("\n--dry-run: nothing was written.")
        return 0

    try:
        saved = save_template(key, payload)
    except ApiError as exc:
        print(f"\nRunPod refused the write: {exc}", file=sys.stderr)
        print("If that says 'not found', the key belongs to a different account than the\n"
              "template's owner (userId on the template record).", file=sys.stderr)
        return 1

    # Prove it landed rather than trusting the mutation's echo.
    fresh = fetch_template(key, saved["id"]) or {}
    live = fresh.get("readme") or ""
    if live.strip() != readme.strip():
        print(f"\nSaved, but the readme read back differently "
              f"({len(live)} vs {len(readme)} chars).", file=sys.stderr)
        return 1
    print(f"\nDone. {saved['id']} now carries the readme ({len(live)} chars).")
    print(f"https://console.runpod.io/hub/template/{saved['id']}")
    ports = fresh.get("ports") or ""
    if PODPANEL_PORT not in ports:
        print(f"note: {PODPANEL_PORT} is still not in the template's ports ({ports})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
