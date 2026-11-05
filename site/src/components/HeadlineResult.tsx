// The study's result, stated on the first screen. It reads the same study/summary.json as the
// study page and shows nothing until that file exists.

import { onLinkClick } from "../app/router";
import { MODEL_NAMES, useStudy } from "../views/Study";

const ROWS: { id: string; name: string; ours: boolean }[] = [
  { id: "A", name: "Schema only", ours: false },
  { id: "B", name: "+ bridge base model", ours: true },
  { id: "S", name: "+ bridge semantics layer", ours: true },
];
const INSIDE: { id: string; name: string; ours: boolean }[] = [
  { id: "C-native", name: "Auto Ontology alone", ours: false },
  { id: "C-base", name: "+ bridge base model", ours: true },
  { id: "C-semantics", name: "+ bridge semantics layer", ours: true },
];

export function HeadlineResult() {
  const data = useStudy();
  if (!data || data === "error") return null;
  const cell = (m: string, a: string) => data.cells.find((c) => c.model === m && c.arm === a);
  const models = Object.keys(MODEL_NAMES).filter((m) => cell(m, "A"));
  if (!models.length) return null;
  const mean = (v: number[]) => v.reduce((a, b) => a + b, 0) / v.length;
  const table = (rows: typeof ROWS, label: string) => (
    <div className="table-wrap">
      <table className="rows headline-cmp__table">
        <thead>
          <tr>
            <th scope="col">{label}</th>
            {models.map((m) => <th key={m} scope="col" className="num">{MODEL_NAMES[m]}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.ours ? "is-ours" : ""}>
              <th scope="row">{r.name}</th>
              {models.map((m) => {
                const c = cell(m, r.id);
                return (
                  <td key={m} className="num cmp-score">
                    {c ? (
                      <>
                        <strong>{mean(c.suite).toFixed(1)}</strong> of {c.denominator}
                        <span className="cmp-bar" aria-hidden="true"><span style={{ width: `${(100 * mean(c.suite)) / c.denominator}%` }} /></span>
                      </>
                    ) : <span className="muted small">running</span>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  const inside = INSIDE.filter((r) => models.some((m) => cell(m, r.id)));
  return (
    <figure className="headline-cmp" aria-labelledby="headline-cmp-cap">
      <figcaption id="headline-cmp-cap" className="headline-cmp__lead">
        48 questions about four Python repositories, written without seeing the bridge and frozen before any model ran. Questions answered
        with the right rows on the real database and on eight altered copies of it, averaged over repeated runs, scored against the
        corrected references:
      </figcaption>
      {table(ROWS, "A model asked directly, given")}
      {inside.length ? table(inside, "NVIDIA’s Auto Ontology agent, 12 questions") : null}
      <p className="small">
        <a href="#/study" onClick={onLinkClick}>How the study was run, every question and every answer</a>
      </p>
    </figure>
  );
}
