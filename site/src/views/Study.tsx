// The code-semantics study (study/PROTOCOL.md): 48 blind-authored questions over four repositories,
// four ways of briefing a model, and NVIDIA Auto Ontology's own agent with and without the bridge.
// Every number comes from study/summary.json, written by study/summarise.py from the run records.

import { useEffect, useState } from "react";
import { Out } from "../components/parts";

const REPO = "https://github.com/wcook04/code-ontology-bridge/blob/main";

export interface Cell {
  model: string;
  arm: string;
  denominator: number;
  repetitions: number;
  snapshot: number[];
  suite: number[];
  snapshot_mean: number;
  suite_mean: number;
  median_seconds: number | null;
  cost_usd: number;
}
interface Pair { model: string; from: string; to: string; questions: number; improved: string[]; regressed: string[] }
interface QItem { id: string; repo: string; question: string; topic: string; difficulty: string }
export interface StudySummary {
  questions: number;
  cells: Cell[];
  paired: Pair[];
  per_question_suite_rate: Record<string, Record<string, number>>;
  question_list: QItem[];
}

export const MODEL_NAMES: Record<string, string> = { deepseek: "DeepSeek v4.1 Flash", nemotron: "NVIDIA Nemotron 3.5 Lightning" };
const DIRECT: { id: string; name: string; what: string }[] = [
  { id: "A", name: "Schema only", what: "Table and column names and types." },
  { id: "B", name: "Bridge base model", what: "Plus what every table and column means, the keys and the joins." },
  { id: "V", name: "Views, undocumented", what: "Schema plus the semantics layer’s views, with no descriptions: a control." },
  { id: "S", name: "Bridge semantics layer", what: "Base model plus verified views for calls, reachability, profiles, dependencies and inheritance, with definitions." },
];
const INSIDE: { id: string; name: string }[] = [
  { id: "C-native", name: "Auto Ontology alone, nothing imported" },
  { id: "C-base", name: "Auto Ontology + bridge base model" },
  { id: "C-semantics", name: "Auto Ontology + bridge semantics layer" },
];
const REPOS: Record<string, string> = { auto_ontology: "NVIDIA Auto Ontology", click: "pallets/click", httpx: "encode/httpx", rich: "Textualize/rich" };

export function useStudy(): StudySummary | null | "error" {
  const [data, setData] = useState<StudySummary | null | "error">(null);
  useEffect(() => {
    fetch(new URL("study/summary.json", document.baseURI)).then(
      (r) => (r.ok ? r.json().then(setData) : setData("error")),
      () => setData("error"),
    );
  }, []);
  return data;
}

function Score({ c, which }: { c?: Cell; which: "snapshot" | "suite" }) {
  if (!c) return <span className="muted small">not run</span>;
  const vals = c[which];
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  return (
    <>
      <strong>{mean.toFixed(1)}</strong> <span className="muted">/ {c.denominator}</span>
      <span className="cmp-bar" aria-hidden="true"><span style={{ width: `${(100 * mean) / c.denominator}%` }} /></span>
      <span className="small muted cmp-range">{vals.length > 1 ? `${Math.min(...vals)}–${Math.max(...vals)} over ${vals.length} runs` : "1 run"}</span>
    </>
  );
}

export function Study() {
  const data = useStudy();
  if (data === null) return <section className="band page"><p className="gate" role="status">Loading the study…</p></section>;
  if (data === "error") return <section className="band page"><p className="gate gate--error" role="alert">The study results could not be loaded.</p></section>;
  const cell = (m: string, a: string) => data.cells.find((c) => c.model === m && c.arm === a);
  const models = Object.keys(MODEL_NAMES).filter((m) => data.cells.some((c) => c.model === m));
  const inside = INSIDE.filter((a) => models.some((m) => cell(m, a.id)));
  return (
    <section className="band page comparison" aria-labelledby="study-title">
      <h1 id="study-title">What the bridge’s semantics change, on questions it never saw</h1>
      <p className="lede-2">
        Four separate AI authors wrote 12 questions each about four Python repositories, from the source and the bare database, without
        seeing what the bridge adds. A second annotator re-derived every answer from the question alone; all 48 agreed, and 17 questions
        were reworded to remove a second reading. The questions, references and{" "}
        <Out href={`${REPO}/study/PROTOCOL.md`}>protocol</Out> were committed and pushed before any model saw them.
      </p>
      <p className="measure">
        Two scores. <strong>Exact rows</strong>: the answer matches the reference rows on the repository’s database.{" "}
        <strong>Robust</strong>: the same SQL also returns the right rows on eight altered copies of that database (extra calls,
        callbacks, same-named functions, removed edges, changed docstrings), so it cannot be right by coincidence.
      </p>

      <h2>Asking a model directly: 48 questions, four repositories, five runs each</h2>
      <ol className="arms">
        {DIRECT.map((a) => (
          <li key={a.id}>
            <span className="arms__n">{a.id}</span>
            <span className="arms__name">{a.name}</span>
            <span className="arms__what">{a.what}</span>
          </li>
        ))}
      </ol>
      {models.map((m) => (
        <section key={m} className="cmp-model" aria-labelledby={`st-${m}`}>
          <h3 id={`st-${m}`}>{MODEL_NAMES[m]}</h3>
          <div className="table-wrap">
            <table className="rows cmp-table">
              <thead>
                <tr><th scope="col">Model is given</th><th scope="col" className="num">Exact rows</th><th scope="col" className="num">Robust</th></tr>
              </thead>
              <tbody>
                {DIRECT.map((a) => (
                  <tr key={a.id} className={a.id === "B" || a.id === "S" ? "is-ours" : ""}>
                    <th scope="row">{a.id}. {a.name}</th>
                    <td className="num cmp-score"><Score c={cell(m, a.id)} which="snapshot" /></td>
                    <td className="num cmp-score"><Score c={cell(m, a.id)} which="suite" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      {inside.length ? (
        <>
          <h2>Inside NVIDIA Auto Ontology: same agent, only the imported model changes</h2>
          <p className="measure">
            The 12 Auto Ontology questions, asked through Auto Ontology’s own SQL agent with its retrieval, validation and repair. The
            agent, database contents and chat model are fixed; three runs each.
          </p>
          <div className="table-wrap">
            <table className="rows cmp-table">
              <thead>
                <tr>
                  <th scope="col">Auto Ontology is given</th>
                  {models.map((m) => <th key={m} scope="col" className="num">{MODEL_NAMES[m]}, robust</th>)}
                </tr>
              </thead>
              <tbody>
                {inside.map((a) => (
                  <tr key={a.id} className={a.id === "C-native" ? "" : "is-ours"}>
                    <th scope="row">{a.name}</th>
                    {models.map((m) => <td key={m} className="num cmp-score"><Score c={cell(m, a.id)} which="suite" /></td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <h2>Question by question</h2>
      <p className="small muted measure">Share of runs whose answer was robustly right. Each column is one model and one briefing.</p>
      <QuestionGrid data={data} models={models} />
      <p className="small muted measure">
        Every question, reference query, annotation, response and score is in the{" "}
        <Out href={`${REPO}/study`}>study folder</Out>; the results page is <Out href={`${REPO}/study/RESULTS.md`}>RESULTS.md</Out>.
      </p>
    </section>
  );
}

function QuestionGrid({ data, models }: { data: StudySummary; models: string[] }) {
  const cols = models.flatMap((m) => ["A", "B", "S", "C-native", "C-base", "C-semantics"].map((a) => ({ m, a, key: `${m}/${a}` })))
    .filter((c) => data.per_question_suite_rate[c.key]);
  return (
    <div className="table-wrap">
      <table className="rows rows--compact">
        <thead>
          <tr>
            <th scope="col">Repository</th>
            <th scope="col" className="cmp-qtext">Question</th>
            {cols.map((c) => (
              <th key={c.key} scope="col" className="num" title={`${MODEL_NAMES[c.m]}, ${c.a}`}>{c.m === "nemotron" ? "N" : "D"}·{c.a.replace("C-", "C ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.question_list.map((q) => (
            <tr key={q.id}>
              <th scope="row" className="small">{REPOS[q.repo]}</th>
              <td className="cmp-qtext small">{q.question}</td>
              {cols.map((c) => {
                const r = data.per_question_suite_rate[c.key]?.[q.id];
                return (
                  <td key={c.key} className={`num ${r === undefined ? "" : r >= 0.5 ? "ok" : "bad"}`}>
                    {r === undefined ? "" : `${Math.round(r * 100)}%`}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
