// The study's result, stated on the first screen. It reads the same study/summary.json as the
// study page and shows nothing until that file exists.

import { onLinkClick } from "../app/router";
import { MODEL_NAMES, useStudy } from "../views/Study";

const ROWS: { id: string; name: string; ours: boolean }[] = [
  { id: "A", name: "Table names only", ours: false },
  { id: "B", name: "+ the bridge’s descriptions", ours: true },
  { id: "S", name: "+ descriptions and explained queries", ours: true },
];
const INSIDE: { id: string; name: string; ours: boolean }[] = [
  { id: "C-native", name: "Nothing from the bridge", ours: false },
  { id: "C-base", name: "+ the bridge’s descriptions", ours: true },
  { id: "C-semantics", name: "+ descriptions and explained queries", ours: true },
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
        We asked two AI models 48 questions about four real Python programs, with and without this project’s description of the
        code. Number of questions answered correctly, counting an answer only if its query also works on eight altered copies of the
        data, averaged over repeated runs:
      </figcaption>
      {table(ROWS, "The AI asked directly, given")}
      {inside.length ? table(inside, "Inside NVIDIA Auto Ontology, 12 questions") : null}
      <p className="small">
        <a href="#/study" onClick={onLinkClick}>How the test was run, every question and every answer</a>
      </p>
    </figure>
  );
}
