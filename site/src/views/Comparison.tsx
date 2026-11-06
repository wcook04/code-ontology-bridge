// The three-arm comparison of docs/experiment-protocol.md: the same model given the schema
// alone, the schema plus this project's semantic model, and Auto Ontology. Every number comes
// from experiment/summary.json, written by tools/summarise_experiment.py from the run records.

import { useEffect, useState } from "react";
import { Out } from "../components/parts";

const REPO = "https://github.com/wcook04/code-ontology-bridge/blob/main";

interface RunRow {
  model: string;
  arm: string;
  set: string;
  questions: number;
  expected_rows: number;
  median_seconds: number | null;
  sql_runs: number;
  requests_repaired: number;
  total_tokens: number | null;
  path: string;
}
interface Summary {
  models: Record<string, string>;
  runs: RunRow[];
  questions: Record<string, Record<string, Record<string, { expected_rows: boolean; rows: number; reference_rows: number }>>>;
  question_text?: Record<string, Record<string, string>>;
  notes?: Record<string, string>;
}

const ARMS: { id: string; name: string; what: string }[] = [
  { id: "schema", name: "Schema only", what: "The model sees table and column names and types, and writes SQL." },
  { id: "schema_model", name: "Schema + exported model", what: "The model also sees this project’s table descriptions: what each table and column means, the keys and the joins." },
  { id: "auto_ontology", name: "Auto Ontology", what: "Auto Ontology imports the table descriptions, and its agent retrieves context, writes, checks and repairs the SQL." },
];
const MODEL_NAMES: Record<string, string> = { nemotron: "NVIDIA Nemotron 3.5 Lightning", deepseek: "DeepSeek v4.1 Flash" };
const SET_NAMES: Record<string, string> = { development: "Development questions", heldout: "Held-out questions" };

export function Comparison() {
  const [data, setData] = useState<Summary | null | "error">(null);
  useEffect(() => {
    fetch(new URL("experiment/summary.json", document.baseURI)).then(
      (r) => (r.ok ? r.json().then(setData) : setData("error")),
      () => setData("error"),
    );
  }, []);
  if (data === null) return <section className="band page"><p className="gate" role="status">Loading the comparison…</p></section>;
  if (data === "error") return <section className="band page"><p className="gate gate--error" role="alert">The comparison results could not be loaded.</p></section>;

  const find = (model: string, arm: string, set: string) => data.runs.find((r) => r.model === model && r.arm === arm && r.set === set);
  const models = Object.keys(MODEL_NAMES).filter((m) => data.runs.some((r) => r.model === m));
  const sets = ["development", "heldout"].filter((s) => data.runs.some((r) => r.set === s));

  return (
    <section className="band page comparison" aria-labelledby="cmp-title">
      <h1 id="cmp-title">What each layer adds</h1>
      <p className="lede-2">
        The same language model answered the same questions three ways, under a{" "}
        <Out href={`${REPO}/docs/experiment-protocol.md`}>protocol committed before any run</Out> and amended only before the runs an
        amendment changed. Each complete run asked every question once, and no question was asked again. A program compared every result
        with a reference query’s rows.
      </p>
      <ol className="arms">
        {ARMS.map((a, i) => (
          <li key={a.id}>
            <span className="arms__n">{String.fromCharCode(65 + i)}</span>
            <span className="arms__name">{a.name}</span>
            <span className="arms__what">{a.what}</span>
          </li>
        ))}
      </ol>
      {models.map((m) => (
        <section key={m} className="cmp-model" aria-labelledby={`cmp-${m}`}>
          <h2 id={`cmp-${m}`}>{MODEL_NAMES[m]}</h2>
          <div className="table-wrap">
            <table className="rows cmp-table">
              <thead>
                <tr>
                  <th scope="col">Arm</th>
                  {sets.map((s) => (
                    <th scope="col" key={s} className="num">
                      {SET_NAMES[s]}
                    </th>
                  ))}
                  <th scope="col" className="num">Median time</th>
                  <th scope="col" className="num">Requests repaired</th>
                </tr>
              </thead>
              <tbody>
                {ARMS.map((a) => {
                  const rows = sets.map((s) => find(m, a.id, s));
                  const all = rows.filter(Boolean) as RunRow[];
                  return (
                    <tr key={a.id}>
                      <th scope="row">{a.name}</th>
                      {rows.map((r, i) => (
                        <td key={sets[i]} className="num cmp-score">
                          {r ? (
                            <>
                              <strong>{r.expected_rows}</strong> of {r.questions}
                              <span className="cmp-bar" aria-hidden="true"><span style={{ width: `${(100 * r.expected_rows) / r.questions}%` }} /></span>
                            </>
                          ) : (
                            <span className="muted">no result</span>
                          )}
                        </td>
                      ))}
                      <td className="num">{all.length ? `${Math.round(Math.max(...all.map((r) => r.median_seconds ?? 0)))} s` : ""}</td>
                      <td className="num">{all.reduce((s, r) => s + r.requests_repaired, 0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {data.notes?.[m] ? <p className="small muted measure">{data.notes[m]}</p> : null}
        </section>
      ))}
      {sets.map((s) => (
        <QuestionGrid key={s} set={s} data={data} models={models} />
      ))}
      <p className="small muted measure">
        Scores count questions whose rows exactly match the reference rows, in order where asked. Median time is the larger of the two
        question sets’ medians. Every response is in the <Out href={`${REPO}/examples/auto-ontology/live/experiment`}>run records</Out>.
      </p>
    </section>
  );
}

function QuestionGrid({ set, data, models }: { set: string; data: Summary; models: string[] }) {
  const qs = data.questions[set] ?? {};
  const ids = Object.keys(qs).sort((a, b) => Number(a) - Number(b));
  const cols = models.flatMap((m) => ARMS.map((a) => ({ key: `${m}/${a.id}`, m, a })));
  return (
    <section className="cmp-grid" aria-labelledby={`grid-${set}`}>
      <h2 id={`grid-${set}`}>{SET_NAMES[set]}, question by question</h2>
      <div className="table-wrap">
        <table className="rows rows--compact">
          <thead>
            <tr>
              <th scope="col">Question</th>
              <th scope="col" className="cmp-qtext">Asked</th>
              {cols.map((c) => (
                <th scope="col" key={c.key} className="num" title={`${MODEL_NAMES[c.m]}, ${c.a.name}`}>
                  {c.m === "nemotron" ? "N" : "D"}
                  {String.fromCharCode(65 + ARMS.indexOf(c.a))}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ids.map((id) => (
              <tr key={id}>
                <th scope="row">{id}</th>
                <td className="cmp-qtext small">{data.question_text?.[set]?.[id] ?? ""}</td>
                {cols.map((c) => {
                  const r = qs[id][c.key];
                  return (
                    <td key={c.key} className={`num ${r ? (r.expected_rows ? "ok" : "bad") : ""}`}>
                      {r ? (r.expected_rows ? "✓" : "✕") : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small muted">N is Nemotron and D is DeepSeek; A, B and C are the three arms above.</p>
    </section>
  );
}
