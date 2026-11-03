"""Send one HTTP request to a running Auto Ontology backend and save request + response as JSON.

Usage:
  python capture.py OUT.json METHOD URL [--body-file PATH] [--json STRING]
                    [--content-type TYPE] [--header NAME:VALUE ...]

The saved file holds the method, URL, request headers, a pointer to (or the
inline text of) the request body, the HTTP status and the parsed response
body. No Authorization or x-api-key header is ever sent by this script.
Prints one summary line: status and a short shape of the response.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("method")
    ap.add_argument("url")
    ap.add_argument("--body-file")
    ap.add_argument("--json")
    ap.add_argument("--content-type")
    ap.add_argument("--header", action="append", default=[])
    ap.add_argument("--timeout", type=float, default=600.0)
    a = ap.parse_args()

    headers: dict[str, str] = {}
    for h in a.header:
        k, _, v = h.partition(":")
        if k.strip().lower() in {"authorization", "x-api-key"}:
            print("capture.py refuses to send credentials", file=sys.stderr)
            return 2
        headers[k.strip()] = v.strip()
    data = None
    body_record: object = None
    if a.body_file:
        data = Path(a.body_file).read_bytes()
        body_record = {"file": a.body_file, "bytes": len(data)}
    elif a.json is not None:
        data = a.json.encode("utf-8")
        body_record = json.loads(a.json)
        headers.setdefault("content-type", "application/json")
    if a.content_type:
        headers["content-type"] = a.content_type

    req = urllib.request.Request(a.url, data=data, method=a.method.upper(), headers=headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=a.timeout) as resp:
            status, raw, ctype = resp.status, resp.read(), resp.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        status, raw, ctype = exc.code, exc.read(), exc.headers.get("content-type", "")
    except urllib.error.URLError as exc:
        status, raw, ctype = None, str(exc.reason).encode(), "text/plain"
    elapsed = round(time.time() - started, 3)
    text = raw.decode("utf-8", "replace")
    try:
        body: object = json.loads(text)
    except ValueError:
        body = text
    record = {
        "request": {"method": a.method.upper(), "url": a.url, "headers": headers, "body": body_record},
        "status": status,
        "content_type": ctype,
        "elapsed_s": elapsed,
        "response": body,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shape = (
        f"keys={sorted(body)[:8]}" if isinstance(body, dict) else f"len={len(body)}" if isinstance(body, list) else text[:120]
    )
    print(f"{a.method.upper()} {a.url} -> {status} ({elapsed}s) {shape}")
    return 0 if status is not None and status < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
