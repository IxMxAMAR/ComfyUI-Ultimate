# Why clicking the ComfyUI link gives a 403 (and pasting it works)

If you click the ComfyUI link on your pod and get an error page, but copying the
same URL and pasting it into the address bar loads fine, nothing is wrong with
your pod, your GPU, or this image. It's a ComfyUI bug, and this image patches it.

## What happens

ComfyUI has a security check in `server.py` that refuses any request carrying
this header:

```
Sec-Fetch-Site: cross-site
```

Browsers add that header by themselves. The catch is that they add it to
ordinary link clicks too, not only to the kind of background request the check
was written for. The RunPod console lives on `console.runpod.io` and your
ComfyUI link is on `*.proxy.runpod.net`, so clicking it counts as cross-site and
ComfyUI answers with `403 Forbidden`.

Pasting the URL into the address bar sends `Sec-Fetch-Site: none` instead, so it
goes through. Same URL, same pod, same second — different header.

That 403 has no body at all, which is why it looks so strange. Firefox throws
the response away and shows its own "Problem loading page", Chrome shows a bare
"HTTP ERROR 403", and neither tells you what actually happened.

## How we know it's ComfyUI and not RunPod

Same pod, same proxy, same moment, three different ports:

| Port | Service | `Sec-Fetch-Site: cross-site` | normal |
|---|---|---|---|
| 8188 | ComfyUI | **403, 0 bytes** | 200 |
| 8888 | JupyterLab | 302 | 302 |
| 8080 | File Browser | 200 | 200 |

RunPod's proxy passes cross-site requests through without complaint — JupyterLab
and File Browser prove that. Only the process on 8188 refuses, and that process
is ComfyUI.

PodPanel (8090) was added later and is not part of the original three-port
comparison. Measured against the panel directly, it answers **200** to `/` and to
`/api/items` both with and without `Sec-Fetch-Site: cross-site`; it never inspects
that header, so this class of 403 cannot apply to it.

ComfyUI is also picky about exactly one header value and nothing else:

| Header sent to ComfyUI | Result |
|---|---|
| no `Sec-Fetch-Site` | 200 |
| `Sec-Fetch-Site: none` | 200 |
| `Sec-Fetch-Site: same-origin` | 200 |
| `Sec-Fetch-Site: same-site` | 200 |
| **`Sec-Fetch-Site: cross-site`** | **403** |
| `Sec-Fetch-User: ?1` on its own | 200 |
| `Sec-Fetch-Mode: navigate` on its own | 200 |
| `Sec-Fetch-Dest: document` on its own | 200 |

## What this image does about it

`scripts/patch_server.py` runs during the build and loosens that one check so it
still refuses cross-site requests but lets a normal page navigation through. A
cross-site GET navigation can't read the response and can't queue a prompt, so
it isn't what the check is protecting against.

Everything else cross-site is still refused. That includes a cross-site form
POST, which arrives looking like a navigation too, so it's checked separately
rather than waved through with the rest.

This is a known upstream issue that isn't fixed yet:
[Comfy-Org/ComfyUI#16203](https://github.com/Comfy-Org/ComfyUI/issues/16203).

## If you're on an older build

Bookmark the ComfyUI URL, or paste it. A bookmark click counts as a
user-initiated navigation rather than one coming from a page, so it loads. Just
don't click the link in the RunPod console.

## Checking it yourself

From a Jupyter or SSH terminal:

```bash
POD=https://<POD_ID>-8188.proxy.runpod.net

# Is ComfyUI itself up?
curl -sI http://localhost:8188/ | head -1        # HTTP/1.1 200 OK

# The click path. Patched: 200. Unpatched: 403.
curl -o /dev/null -w '%{http_code}\n' \
  -H 'Sec-Fetch-Site: cross-site' -H 'Sec-Fetch-Mode: navigate' $POD/

# A cross-site POST. Should be 403 either way.
curl -o /dev/null -w '%{http_code}\n' -X POST \
  -H 'Sec-Fetch-Site: cross-site' -H 'Content-Type: application/json' \
  -d '{}' $POD/prompt
```
