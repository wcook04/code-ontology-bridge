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
        allowed(params, ["q", "limit", "offset", *columns, *(["target"] if name == "calls" else [])])
        target = params.get("target", "all")
        if target not in ("all", "resolved", "null"):
            raise APIError(400, "target must be all, resolved or null")
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
                if (target == "all" or (r["callee_symbol_id"] is not None) == (target == "resolved"))
                and all(r[k] == v for k, v in filters.items())
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
        distances, queue = {root: 0}, deque([root])
        omissions = set()

        def eligible(edge):
            if kind != "all" and edge["call_kind"] != kind:
                return False
            # Root remains visible even if it is a test; other test symbols do not expand.
            return include_tests or all(s == root or not self.files[self.symbols[s]["file_id"]]["is_test"]
                                        for s in (edge["caller_symbol_id"], edge["callee_symbol_id"]))

        while queue:
            current = queue.popleft()
            if distances[current] == depth:
                continue
            for edge in sorted(adjacency[current], key=lambda e: e["call_id"]):
                target = edge[neighbor]
                if not eligible(edge) or target in distances:
                    continue
                if len(distances) >= max_nodes:
                    omissions.add("node_limit")
                    continue
                distances[target] = distances[current] + 1
                queue.append(target)
        # Induced edges include cycles at the boundary and parallel call occurrences.
        candidates = {}
        for current in distances:
            for edge in adjacency[current]:
                if not eligible(edge):
                    continue
                if edge[neighbor] in distances:
                    candidates[edge["call_id"]] = edge
                elif distances[current] == depth:
                    omissions.add("depth_limit")
        selected = [candidates[k] for k in sorted(candidates)][:max_edges]
        if len(selected) < len(candidates):
            omissions.add("edge_limit")
        edges = []
        for edge in selected:
            caller = self.symbols[edge["caller_symbol_id"]]
            edges.append(dict(edge, source_url=self.source_url({"file_id": caller["file_id"],
                              "line_start": edge.get("line", caller.get("line_start", 1))})))
        return {
            "root": root, "direction": direction, "depth": depth,
            "call_kind": kind, "include_tests": include_tests,
            "test_policy": "include" if include_tests else "exclude_from_traversal_except_root",
            "max_nodes": max_nodes, "max_edges": max_edges,
            "edge_semantics": "induced_call_occurrences", "availability": "computed_locally",
            "truncated": bool(omissions & {"node_limit", "edge_limit"}),
            "depth_limited": "depth_limit" in omissions, "omission_reasons": sorted(omissions),
            "counts": {"nodes": len(distances), "call_occurrences": len(edges),
                       "unique_pairs": len({(e["caller_symbol_id"], e["callee_symbol_id"]) for e in edges}),
                       "eligible_call_occurrences": len(candidates)},
            "nodes": [dict(self.symbols[s], depth=d, source_url=self.source_url(self.symbols[s]))
                      for s, d in sorted(distances.items(), key=lambda item: (item[1], item[0]))],
            "edges": edges,
            "semantics": "Resolved static relationships; arrows remain caller-to-callee. Callback references do not establish execution.",
        }

    def query(self, path, params):
        if path == PREFIX:
            allowed(params, [])
            return {"snapshot": self.bundle["snapshot"], "routes": {
                "overview": PREFIX + "/overview", "schema": PREFIX + "/schema",
                "tables": PREFIX + "/tables/{table}", "graph": PREFIX + "/graph",
                "questions": PREFIX + "/questions", "question": PREFIX + "/questions/{id}",
                "bundle": PREFIX + "/bundle", "openapi": PREFIX + "/openapi.json",
                "outcomes": PREFIX + "/outcomes", "walkthrough": PREFIX + "/walkthroughs/{case_id}",
                "walkthrough_step": PREFIX + "/walkthroughs/{case_id}/steps/{step_id}",
                "models": PREFIX + "/models", "cases": PREFIX + "/cases", "source_spans": PREFIX + "/source-spans"},
                "limits": {"page_size": 100, "graph_depth": 5, "graph_nodes": 200, "graph_edges": 500},
                "execution": "unavailable", "contract": "docs/inspection-api.md"}
        if path == PREFIX + "/outcomes":
            from .walkthrough import outcomes
            return outcomes(self, params)
        if path.startswith(PREFIX + "/walkthroughs/"):
            from .walkthrough import walkthrough
            allowed(params, [])
            parts = path.removeprefix(PREFIX + "/walkthroughs/").split("/")
            result = walkthrough(self, parts[0])
            if len(parts) == 1:
                return result
            if len(parts) == 3 and parts[1] == "steps":
                for step in result["steps"]:
                    if step["id"] == parts[2]:
                        return step
            raise APIError(404, "walkthrough step not found")
        if path == PREFIX + "/graph":
            return self.graph(params)
        if path.startswith(PREFIX + "/tables/"):
            return self.table(path.removeprefix(PREFIX + "/tables/"), params)
        if path == PREFIX + "/questions":
            allowed(params, ["limit", "offset"])
            return self.page([{k: q[k] for k in ("question_id", "question", "score", "review_finding", "assessment") if k in q}
                              for q in self.questions.values()], params)
        if path.startswith(PREFIX + "/questions/"):
            allowed(params, [])
            qid = path.removeprefix(PREFIX + "/questions/")
            if qid not in self.questions:
                raise APIError(404, "question not found")
            return self.questions[qid]
        allowed(params, [])
        if path == PREFIX + "/models":
            return self.bundle.get("models", {})
        if path == PREFIX + "/cases":
            return self.bundle.get("cases", [])
        if path == PREFIX + "/source-spans":
            return self.bundle.get("source_spans", [])
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
                    "dataset": self.bundle.get("dataset"),
                    "evidence": {k: v for k, v in self.bundle["evidence"].items() if k not in ("questions", "contracts")}}
        raise APIError(404, "route not found")

    def response(self, path, params):
        return {"schema_version": API_SCHEMA, "revision": self.revision,
                "data": self.query(path, params)}
