"""Small reading projections over the existing snapshot; no execution or new evidence."""
from collections import Counter

from .api import APIError, PREFIX, allowed


def outcomes(api, params):
    allowed(params, ["q", "table_match", "prose_review", "limit", "offset"])
    for field, values in (("table_match", ("pass", "fail", "unknown")),
                          ("prose_review", ("substantive", "fail", "unknown"))):
        if field in params and params[field] not in values:
            raise APIError(400, "invalid " + field)
    query = params.get("q", "").strip().casefold()
    if "q" in params and (not query or len(query) > 160):
        raise APIError(400, "q must contain 1–160 nonblank characters")
    rows = []
    for question in sorted(api.questions.values(), key=lambda q: q["question_id"]):
        qid = question["question_id"]
        rows.append({k: question[k] for k in ("question_id", "question", "assessment", "score", "review_finding")} | {
            "question_route": f"{PREFIX}/questions/{qid}",
            "walkthrough_routes": [f"{PREFIX}/walkthroughs/{c['id']}" for c in api.bundle.get("cases", []) if c["question_id"] == qid]})
    counts = {field: dict(Counter(r["assessment"][field] for r in rows)) for field in ("table_match", "prose_review")}
    matched = [r for r in rows if all(r["assessment"][k] == params[k] for k in ("table_match", "prose_review") if k in params)
               and (not query or query in (f"Q{r['question_id']} " + r["question"]).casefold())]
    return dict(api.page(matched, params), population_total=len(rows), population_counts=counts,
                scope=api.bundle["evidence"].get("scope", "No recorded run supplied."),
                note="Counts describe the complete recorded run, not the filtered page. Table matching and author prose review are separate judgments.")


def walkthrough(api, case_id):
    case = next((c for c in api.bundle.get("cases", []) if c["id"] == case_id), None)
    if case is None:
        raise APIError(404, "walkthrough not found")
    question = api.questions[str(case["question_id"])]
    models = api.bundle.get("models", {})
    model = models.get("exported_input", {})
    document = model.get("document", {})
    semantic = document.get("semantic_layer", {})
    tables = [t for db in document.get("data_layer", {}).get("databases", []) for s in db["schemas"] for t in s["tables"]]
    terms = [t for t in semantic.get("terms", []) if t["id"] in case["semantic_term_ids"]]
    represented = {identity for term in terms for identity in term["represents"]}
    spans = [s for s in api.bundle.get("source_spans", []) if s["id"] in case["source_span_ids"]]
    route = f"{PREFIX}/walkthroughs/{case_id}"
    steps = [
        ("source", "Source", "snapshot", {"spans": spans, "focus_span_ids": ["call:" + c for c in case["call_ids"]]}),
        ("records", "Extracted rows", "computed_locally", {"records": case["records"], "graphs": case["graphs"], "note": case["note"]}),
        ("model", "Semantic model", model.get("status", "not_supplied"), {
            "terms": terms, "tables": [t for t in tables if t["id"] in represented],
            "column_ids": case["column_ids"], "semantic_fks": semantic.get("semantic_fks", []),
            "exported_input": {k: v for k, v in model.items() if k not in ("text", "document")},
            "stages": {k: v for k, v in models.items() if k not in ("exported_input", "generated_export")},
            "full_model_route": PREFIX + "/models"}),
        ("request", "Exact submitted request", "recorded", {"request": question["request"], "output_contract": question["output_contract"]}),
        ("sql", "Recorded SQL", "recorded", {"sql": question["sql"], "reference_sql": question["reference_sql"],
            "note": "Generated SQL and reference SQL are retained separately. This endpoint executes neither."}),
        ("answer", "Rows, answer and assessment", "recorded", {k: question[k] for k in (
            "result_tables", "answer", "reference_rows", "assessment", "score", "review_finding", "display_annotations")}),
    ]
    return {"id": case_id, "title": case["title"], "short_question": case["short_question"],
            "question_id": case["question_id"], "question_route": f"{PREFIX}/questions/{case['question_id']}",
            "snapshot": api.bundle["snapshot"], "recorded_response_ref": case["recorded_response_ref"],
            "binding": api.bundle["evidence"].get("binding"), "editorial": True, "captions": case["captions"],
            "steps": [{"id": key, "title": title, "availability": availability, "route": route + "/steps/" + key,
                       "previous": steps[i - 1][0] if i else None, "next": steps[i + 1][0] if i + 1 < len(steps) else None,
                       "data": data} for i, (key, title, availability, data) in enumerate(steps)],
            "note": "This reading order is editorial, not a captured execution trace. Missing historical stages remain explicit. Graphs are local static computations; SQL and answers are saved outputs."}
