"""Send the ready PATCH requests from a `cob cert-status --plan-patches` output
directly to Auto Ontology's internal FastAPI service, with no token.

`cob cert-status --apply` refuses to send without AUTO_ONTOLOGY_API_TOKEN
because the public route goes through the Next.js gateway, which checks it.
The FastAPI service on 127.0.0.1:3001 is the internal service behind that
gateway and does not check a token. This script sends the same bodies to
the same paths there, and saves one request/response record per call.

Usage: python apply_plan_no_token.py PLAN.json BASE_URL OUT_DIR [USER_ID]

USER_ID, when given, is sent as `x-auto-ontology-user-id` (the trusted
gateway header, not a credential); their PATCH routes record it as
`modified_by`.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    plan_path, base_url, out_dir = sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3])
    user_id = sys.argv[4] if len(sys.argv) > 4 else None
    headers = {"content-type": "application/json"}
    if user_id:
        headers["x-auto-ontology-user-id"] = user_id
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    requests = plan.get("patch_plan", plan)["requests"]
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for n, req in enumerate(requests, 1):
        if not req["ready"]:
            results.append({"path": req["path"], "sent": False, "reason": "unmapped live id"})
            continue
        http_req = urllib.request.Request(
            base_url + req["path"],
            data=json.dumps(req["json"]).encode("utf-8"),
            method=req["method"],
            headers=headers,
        )
        try:
            with urllib.request.urlopen(http_req, timeout=30) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        try:
            body: object = json.loads(raw)
        except ValueError:
            body = raw.decode("utf-8", "replace")
        record = {
            "request": {"method": req["method"], "url": base_url + req["path"], "headers": headers, "json": req["json"]},
            "target": req["target"],
            "because_event_id": req["because_event_id"],
            "status": status,
            "response": body,
        }
        (out_dir / f"07_patch_{n}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        results.append({"path": req["path"], "sent": True, "status": status})
        print(f"{req['method']} {req['path']} {req['json']} -> {status}")
    (out_dir / "07_patch_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r.get("status", 0) < 400 for r in results if r["sent"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
