// The comparison's held-out result, stated on the first screen. It reads the same
// experiment/summary.json as the comparison page and shows nothing until that file exists.

import { useEffect, useState } from "react";
import { onLinkClick } from "../app/router";

interface RunRow { model: string; arm: string; set: string; questions: number; expected_rows: number }

const ARMS: { id: string; name: string }[] = [
  { id: "schema", name: "Schema only" },
  { id: "schema_model", name: "Schema + this project’s semantic model" },
  { id: "auto_ontology", name: "Auto Ontology, with the semantic model imported" },
];
const MODELS: { id: string; name: string }[] = [
  { id: "nemotron", name: "NVIDIA Nemotron 3.5 Lightning" },
  { id: "deepseek", name: "DeepSeek v4.1 Flash" },
];

export function HeadlineResult() {
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  useEffect(() => {
    fetch(new URL("experiment/summary.json", document.baseURI)).then(
      (r) => (r.ok ? r.json().then((d) => setRuns(d.runs)) : undefined),
      () => undefined,
    );
  }, []);
  if (!runs) return null;
  const held = (m: string, a: string) => runs.find((r) => r.model === m && r.arm === a && r.set === "heldout");
  const arms = ARMS.filter((a) => MODELS.some((m) => held(m.id, a.id)));
  if (arms.length < 2) return null;
  const n = held(MODELS[0].id, arms[0].id)!.questions;
  return (
    <figure className="headline-cmp" aria-labelledby="headline-cmp-cap">
      <figcaption id="headline-cmp-cap" className="headline-cmp__lead">
        {n} held-out questions about Auto Ontology’s own code, committed before any model saw them and asked without hints. Questions
        answered with exactly the right rows:
      </figcaption>
      <div className="table-wrap">
        <table className="rows headline-cmp__table">
          <thead>
            <tr>
              <th scope="col">What the model was given</th>
              {MODELS.map((m) => (
                <th scope="col" className="num" key={m.id}>{m.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {arms.map((a) => (
              <tr key={a.id} className={a.id === "schema" ? "" : "is-ours"}>
                <th scope="row">{a.name}</th>
                {MODELS.map((m) => {
                  const r = held(m.id, a.id);
                  return (
                    <td className="num cmp-score" key={m.id}>
                      {r ? (
                        <>
                          <strong>{r.expected_rows}</strong> of {r.questions}
                          <span className="cmp-bar" aria-hidden="true"><span style={{ width: `${(100 * r.expected_rows) / r.questions}%` }} /></span>
                        </>
                      ) : (
                        <span className="muted small">no result*</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {arms.some((a) => MODELS.some((m) => !held(m.id, a.id))) ? (
        <p className="small muted">* Nemotron’s held-out run inside Auto Ontology was rate-limited by the NVIDIA API and is not counted; the comparison page explains.</p>
      ) : null}
      <p className="small">
        <a href="#/comparison" onClick={onLinkClick}>
          How the comparison was run, the 22 development questions and every answer
        </a>
      </p>
    </figure>
  );
}
