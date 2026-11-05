"""Score every completed run and write study/results/summary.json and study/results/scores.json.

Per model and arm: snapshot and suite accuracy over all 48 questions for each repetition (mean, min, max),
per repository, per-question majority outcome, paired question-level wins and losses between arms,
latency, tokens and cost.

usage: python study/summarise.py [--runs build/study/runs] [--c-runs build/c]
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "study"))
from score import score_run  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--runs", type=Path, default=ROOT / "build/study/runs")
p.add_argument("--c-runs", type=Path, default=ROOT / "build/c")
p.add_argument("--fuzz-dir", type=Path, default=ROOT / "build/study/fuzz")
p.add_argument("--out", type=Path, default=ROOT / "study/results")
a = p.parse_args()
questions = {q["id"]: q for q in json.loads((ROOT / "study/questions/questions.json").read_text())}

scores = []
for m in sorted(a.runs.glob("*/*/*/r*/complete.json")):
    run = m.parent
    s = score_run(run, questions, a.fuzz_dir)
    s.update(model_key=run.parts[-4], arm=run.parts[-3], rep=int(run.name[1:]))
    scores.append(s)
for m in sorted(a.c_runs.glob("*-*-*/complete.json")):
    run = m.parent
    if not (run / "responses").exists() or json.loads(m.read_text()).get("exit_code") != 0:
        continue
    model_key, variant, rep = run.name.split("-")
    s = score_run(run, questions, a.fuzz_dir)
    s.update(model_key=model_key, arm=f"C-{variant}", rep=int(rep))
    scores.append(s)

# Group: (model, arm, rep) -> list of per-question results across repos.
by = defaultdict(list)
for s in scores:
    by[(s["model_key"], s["arm"], s["rep"])].extend((s["repo"], q) for q in s["questions"])

summary = {"questions": len(questions), "cells": []}
cell_q = {}
for model in sorted({k[0] for k in by}):
    for arm in ["A", "B", "V", "S", "C-native", "C-base", "C-semantics"]:
        reps = sorted(r for (mm, aa, r) in by if mm == model and aa == arm)
        if not reps:
            continue
        expected = 12 if arm.startswith("C") else 48
        complete = [r for r in reps if len(by[(model, arm, r)]) == expected]
        if not complete:
            continue
        snap = [sum(q["snapshot"] for _, q in by[(model, arm, r)]) for r in complete]
        suite = [sum(q["suite"] for _, q in by[(model, arm, r)]) for r in complete]
        per_q = defaultdict(list)
        lat, cost, ptok = [], 0.0, 0
        for r in complete:
            for repo, q in by[(model, arm, r)]:
                per_q[q["id"]].append(q)
                if q["elapsed_s"] is not None:
                    lat.append(q["elapsed_s"])
                cost += q["cost"] or 0
                ptok += q["prompt_tokens"] or 0
        cell_q[(model, arm)] = {qid: sum(x["suite"] for x in v) / len(v) for qid, v in per_q.items()}
        per_repo = {}
        for repo in ["auto_ontology", "click", "httpx", "rich"]:
            vals = [sum(q["suite"] for rp, q in by[(model, arm, r)] if rp == repo) for r in complete]
            if any(rp == repo for rp, _ in by[(model, arm, complete[0])]):
                per_repo[repo] = statistics.mean(vals)
        summary["cells"].append({
            "model": model, "arm": arm, "denominator": expected, "repetitions": len(complete),
            "snapshot": snap, "suite": suite,
            "snapshot_mean": statistics.mean(snap), "suite_mean": statistics.mean(suite),
            "suite_per_repo_mean": per_repo,
            "median_seconds": statistics.median(lat) if lat else None,
            "cost_usd": round(cost, 4), "prompt_tokens_per_request": round(ptok / max(1, len(complete) * expected)),
        })

pairs = []
for model in sorted({k[0] for k in cell_q}):
    for x, y in [("C-native", "C-base"), ("C-native", "C-semantics"), ("A", "B"), ("B", "S"), ("A", "S"), ("V", "S"), ("A", "V"), ("C-base", "C-semantics")]:
        if (model, x) in cell_q and (model, y) in cell_q:
            qx, qy = cell_q[(model, x)], cell_q[(model, y)]
            common = sorted(set(qx) & set(qy))
            better = [q for q in common if qy[q] - qx[q] >= 0.5]
            worse = [q for q in common if qx[q] - qy[q] >= 0.5]
            pairs.append({"model": model, "from": x, "to": y, "questions": len(common),
                          "improved": better, "regressed": worse,
                          "mean_suite_rate_change": round(sum(qy[q] - qx[q] for q in common) / len(common), 4)})
summary["paired"] = pairs
summary["question_list"] = [{"id": q["id"], "repo": q["repo"], "question": q["question"], "topic": q["topic"],
                             "difficulty": q["difficulty"]} for q in questions.values()]
summary["per_question_suite_rate"] = {f"{m}/{arm}": v for (m, arm), v in cell_q.items()}
a.out.mkdir(parents=True, exist_ok=True)
(a.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
(a.out / "scores.json").write_text(json.dumps(scores, indent=2) + "\n")
for c in summary["cells"]:
    print(f"{c['model']:<9} {c['arm']:<12} n={c['repetitions']}  snapshot {c['snapshot_mean']:.1f}/{c['denominator']} {c['snapshot']}  "
          f"suite {c['suite_mean']:.1f}/{c['denominator']} {c['suite']}  median {c['median_seconds']}s  ${c['cost_usd']}")
for pr in pairs:
    print(f"{pr['model']:<9} {pr['from']}->{pr['to']}: improved {len(pr['improved'])}, regressed {len(pr['regressed'])}, mean change {pr['mean_suite_rate_change']:+.3f}")
