"""Transport-independent inspection queries over a detached, indexed snapshot."""
from __future__ import annotations

from collections import defaultdict, deque
import copy
import re
from urllib.parse import quote

from ..codemap.schema import TABLES_BY_NAME

PREFIX = "/api/v1"
API_SCHEMA = "cob_inspection_api_v1"


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def number(params, key, default, minimum, maximum):
    value = params.get(key, str(default))
    if not re.fullmatch(r"[0-9]{1,9}", value) or not minimum <= int(value) <= maximum:
        raise APIError(400, f"{key} must be between {minimum} and {maximum}")
    return int(value)


def boolean(params, key, default):
    value = params.get(key, str(default).lower())
    if value not in ("true", "false"):
        raise APIError(400, f"{key} must be true or false")
    return value == "true"


def allowed(params, names):
    if set(params) - set(names):
        raise APIError(400, "unknown query parameter")


class Inspector:
    def __init__(self, bundle):
        self.bundle = copy.deepcopy(bundle)
        self.revision = self.bundle["revision"]
        self.tables = self.bundle["tables"]
        self.files = {r["file_id"]: r for r in self.tables["files"]}
        self.symbols = {r["symbol_id"]: r for r in self.tables["symbols"]}
        self.questions = {str(r["question_id"]): r for r in self.bundle["evidence"]["questions"]}
        self.incoming, self.outgoing = defaultdict(list), defaultdict(list)
        for call in self.tables["calls"]:
            if call["callee_symbol_id"]:
                self.incoming[call["callee_symbol_id"]].append(call)
                self.outgoing[call["caller_symbol_id"]].append(call)

    def source_url(self, row):
        snapshot = self.bundle["snapshot"]
        repo = snapshot["repo_url"].removesuffix(".git")
        commit = snapshot.get("commit_sha") or ""
        if repo.startswith("git@github.com:"):
            repo = "https://github.com/" + repo.split(":", 1)[1]
        if not re.fullmatch(r"https://github.com/[\w.-]+/[\w.-]+", repo) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            return None
        path = row["file_id"]
        if path.startswith("/") or ".." in path.split("/"):
            return None
        return f"{repo}/blob/{commit}/{quote(path, safe='/')}#L{row.get('line_start', 1)}"

    def page(self, rows, params):
        limit = number(params, "limit", 25, 1, 100)
        offset = number(params, "offset", 0, 0, 999999999)
        end = offset + limit
        return {"items": rows[offset:end], "total": len(rows), "limit": limit,
                "offset": offset, "next_offset": end if end < len(rows) else None}

    def table(self, name, params):
        if name not in TABLES_BY_NAME:
            raise APIError(404, "table not found")
        columns = TABLES_BY_NAME[name].column_names
        allowed(params, ["q", "limit", "offset", *columns])
        query = params.get("q", "").strip().casefold()
        if "q" in params and (not query or len(query) > 160):
            raise APIError(400, "q must contain 1–160 nonblank characters")
        filters = {}
        for col in TABLES_BY_NAME[name].columns:
            if col.name not in params:
                continue
            if col.sql_type == "BOOLEAN":
                filters[col.name] = boolean(params, col.name, False)
            elif col.sql_type == "INTEGER":
                filters[col.name] = number(params, col.name, 0, 0, 999999999)
            else:
                filters[col.name] = params[col.name]
        rows = [r for r in self.tables[name]
                if all(r[k] == v for k, v in filters.items())
                and (not query or any(query in str(v).casefold() for v in r.values() if v is not None))]
        result = self.page(rows, params)
        if name in ("files", "symbols"):
            result["items"] = [dict(r, source_url=self.source_url(r)) for r in result["items"]]
        return result

    def graph(self, params):
        allowed(params, ["symbol_id", "direction", "depth", "max_nodes", "max_edges", "include_tests", "call_kind"])
        root = params.get("symbol_id")
        if root not in self.symbols:
            raise APIError(404, "symbol not found")
        direction = params.get("direction", "callers")
        kind = params.get("call_kind", "all")
        if direction not in ("callers", "callees") or kind not in ("all", "direct", "callback"):
            raise APIError(400, "invalid graph direction or call_kind")
        depth = number(params, "depth", 1, 1, 5)
        max_nodes = number(params, "max_nodes", 100, 1, 200)
        max_edges = number(params, "max_edges", 200, 1, 500)
        include_tests = boolean(params, "include_tests", True)
        adjacency = self.incoming if direction == "callers" else self.outgoing
        neighbor = "caller_symbol_id" if direction == "callers" else "callee_symbol_id"
        distances, edges, queue = {root: 0}, {}, deque([root])
        truncated = depth_limited = False
        while queue:
            current = queue.popleft()
            for edge in adjacency[current]:
                target = edge[neighbor]
                if kind != "all" and edge["call_kind"] != kind:
                    continue
                if not include_tests and self.files[self.symbols[target]["file_id"]]["is_test"]:
                    continue
                if distances[current] == depth:
                    depth_limited |= target not in distances
                    continue
                if edge["call_id"] in edges:
                    continue
                if len(edges) >= max_edges or (target not in distances and len(distances) >= max_nodes):
                    truncated = True
                    continue
                edges[edge["call_id"]] = edge
                if target not in distances:
                    distances[target] = distances[current] + 1
                    queue.append(target)
        return {
            "root": root, "direction": direction, "depth": depth,
            "truncated": truncated, "depth_limited": depth_limited,
            "nodes": [dict(self.symbols[s], depth=d, source_url=self.source_url(self.symbols[s]))
                      for s, d in sorted(distances.items(), key=lambda item: (item[1], item[0]))],
            "edges": [edges[k] for k in sorted(edges)],
            "semantics": "Resolved static relationships; arrows remain caller-to-callee. Callback references do not establish execution.",
        }

    def query(self, path, params):
        if path == PREFIX:
            allowed(params, [])
            return {"snapshot": self.bundle["snapshot"], "routes": {
                "overview": PREFIX + "/overview", "schema": PREFIX + "/schema",
                "tables": PREFIX + "/tables/{table}", "graph": PREFIX + "/graph",
                "questions": PREFIX + "/questions", "question": PREFIX + "/questions/{id}",
                "bundle": PREFIX + "/bundle", "openapi": PREFIX + "/openapi.json"},
                "limits": {"page_size": 100, "graph_depth": 5, "graph_nodes": 200, "graph_edges": 500},
                "execution": "unavailable", "contract": "docs/inspection-api.md"}
        if path == PREFIX + "/graph":
            return self.graph(params)
        if path.startswith(PREFIX + "/tables/"):
            return self.table(path.removeprefix(PREFIX + "/tables/"), params)
        if path == PREFIX + "/questions":
            allowed(params, ["limit", "offset"])
            return self.page([{k: q[k] for k in ("question_id", "question", "score", "review_finding")}
                              for q in self.questions.values()], params)
        if path.startswith(PREFIX + "/questions/"):
            allowed(params, [])
            qid = path.removeprefix(PREFIX + "/questions/")
            if qid not in self.questions:
                raise APIError(404, "question not found")
            return self.questions[qid]
        allowed(params, [])
        if path == PREFIX + "/schema":
            return self.bundle["schema"]
        if path == PREFIX + "/bundle":
            return self.bundle
        if path == PREFIX + "/overview":
            packages = defaultdict(lambda: {"files": 0, "symbols": 0})
            for row in self.files.values():
                packages[row["package"]]["files"] += 1
            for row in self.symbols.values():
                packages[self.files[row["file_id"]]["package"]]["symbols"] += 1
            return {"snapshot": self.bundle["snapshot"], "summary": self.bundle["summary"],
                    "packages": [dict(package=k, **v) for k, v in sorted(packages.items())],
                    "evidence": {k: v for k, v in self.bundle["evidence"].items() if k != "questions"}}
        raise APIError(404, "route not found")

    def response(self, path, params):
        return {"schema_version": API_SCHEMA, "revision": self.revision,
                "data": self.query(path, params)}
