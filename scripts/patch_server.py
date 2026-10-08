#!/usr/bin/env python3
"""Stop ComfyUI's origin-only middleware from 403-ing link clicks.

ComfyUI ships create_origin_only_middleware() in server.py, and it rejects EVERY
request whose Sec-Fetch-Site header is 'cross-site' with a bare, body-less 403:

    if 'Sec-Fetch-Site' in request.headers:
        sec_fetch_site = request.headers['Sec-Fetch-Site']
        if sec_fetch_site == 'cross-site':
            return web.Response(status=403)

That is far too broad. A cross-site *top-level navigation* - a user following a
link to this ComfyUI from another site, which is exactly what the RunPod
console's "Connect to HTTP Service" link does - is not the attack this
middleware exists to stop. The middleware's own comment names the target: "a
random website can queue comfy workflows by making a POST to 127.0.0.1". A
GET/HEAD navigation cannot read the response and cannot queue anything (queueing
is POST /prompt), so letting it through costs nothing.

Symptom this fixes: clicking the ComfyUI link in the RunPod console returns a
bare 403 with Content-Length: 0, which Firefox renders as about:neterror
"Problem loading page" and Chrome as a generic HTTP ERROR 403. Typing or pasting
the same URL works, because that sends Sec-Fetch-Site: none.

Verified byte-identical at v0.35.1, v0.37.4, v0.39.2 and current master, so the
anchor below holds across the versions this image has pinned.

Upstream: https://github.com/Comfy-Org/ComfyUI/issues/16203

This rewrite admits only safe top-level navigations and keeps blocking every
other cross-site request. Idempotent.
"""
import os
import sys

# Path is overridable so the patch can be tested outside the image (CI/local);
# inside the Docker build the default is what is used.
SERVER_PY = os.environ.get("COMFY_SERVER_PY") or (
    sys.argv[1] if len(sys.argv) > 1 else "/ComfyUI/server.py"
)
MARKER = "# PATCHED-CROSS-SITE-NAV"

ORIGINAL = """        if 'Sec-Fetch-Site' in request.headers:
            sec_fetch_site = request.headers['Sec-Fetch-Site']
            if sec_fetch_site == 'cross-site':
                return web.Response(status=403)
"""

PATCHED = """        if 'Sec-Fetch-Site' in request.headers:
            sec_fetch_site = request.headers['Sec-Fetch-Site']
            if sec_fetch_site == 'cross-site':
                # PATCHED-CROSS-SITE-NAV: allow safe top-level navigations.
                # Following a link to this ComfyUI from another site (e.g. the
                # RunPod console) is a cross-site GET navigation. It cannot
                # read the response and cannot queue a workflow - queueing is
                # POST /prompt - so it is not the CSRF vector this middleware
                # guards against. All other cross-site requests still 403.
                # Upstream: Comfy-Org/ComfyUI#16203
                if not (
                    request.method in ('GET', 'HEAD')
                    and request.headers.get('Sec-Fetch-Mode') == 'navigate'
                ):
                    return web.Response(status=403)
"""


def main() -> int:
    try:
        with open(SERVER_PY, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        print(f"ERROR: cannot read {SERVER_PY}: {e}", file=sys.stderr)
        return 1

    if MARKER in src:
        print("patch_server: already patched, nothing to do")
        return 0

    if ORIGINAL not in src:
        print(
            "ERROR: the origin-only middleware block was not found in\n"
            f"       {SERVER_PY}\n"
            "       ComfyUI has most likely changed or fixed this code.\n"
            "       Check https://github.com/Comfy-Org/ComfyUI/issues/16203\n"
            "       and, if the fix has landed upstream, delete this script\n"
            "       and the RUN line that calls it from the Dockerfile.\n"
            "       Failing the build on purpose so this cannot ship broken.",
            file=sys.stderr,
        )
        return 1

    with open(SERVER_PY, "w", encoding="utf-8") as f:
        f.write(src.replace(ORIGINAL, PATCHED, 1))

    print("patch_server: cross-site top-level navigations now allowed (GET/HEAD only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
