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
  cost_usd: number | null;
}
interface Pair { model: string; from: string; to: string; questions: number; improved: string[]; regressed: string[] }
interface QItem { id: string; repo: string; label?: string; question: string; topic: string; difficulty: string }
export interface StudySummary {
  evaluator?: string;
  questions: number;
  cells: Cell[];
  paired: Pair[];
  per_question_suite_rate: Record<string, Record<string, number>>;
  question_list: QItem[];
}

export const MODEL_NAMES: Record<string, string> = { deepseek: "DeepSeek v4.1 Flash", nemotron: "NVIDIA Nemotron 3.5 Lightning" };
const DIRECT: { id: string; name: string; what: string }[] = [
  { id: "A", name: "Table names only", what: "The names of the tables and columns, nothing more." },
  { id: "B", name: "+ table descriptions", what: "What every table and column means, each table’s key, and how the tables join." },
  { id: "V", name: "+ ready-made queries, without descriptions", what: "Six SQL views (for example “which functions can reach which”), listed by name only." },
  { id: "S", name: "+ table descriptions and ready-made queries", what: "The table descriptions plus the six views, each described." },
];
const INSIDE: { id: string; name: string; what: string }[] = [
  { id: "C-native", name: "The code database, nothing imported", what: "Auto Ontology reads the bridge’s code database and works out what it means by itself." },
  { id: "C-base", name: "+ table descriptions", what: "The table descriptions are imported as well." },
  { id: "C-semantics", name: "+ table descriptions and ready-made queries", what: "The six views are added to the database and described in the import." },
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

function mean(v: number[]): number {
  return v.reduce((a, b) => a + b, 0) / v.length;
}

function Score({ c }: { c?: Cell }) {
  if (!c) return <span className="muted small">not run</span>;
  const m = mean(c.suite);
  return (
    <>
      <strong>{m.toFixed(1)}</strong> <span className="muted">of {c.denominator}</span>
      <span className="cmp-bar" aria-hidden="true"><span style={{ width: `${(100 * m) / c.denominator}%` }} /></span>
      <span className="small muted cmp-range">
        between {Math.min(...c.suite)} and {Math.max(...c.suite)} across runs
      </span>
    </>
  );
}

function ResultTable({ rows, models, cell, label }: {
  rows: { id: string; name: string; what: string }[];
  models: string[];
  cell: (m: string, a: string) => Cell | undefined;
  label: string;
}) {
  return (
    <div className="table-wrap">
      <table className="rows cmp-table study-table">
        <thead>
          <tr>
            <th scope="col">{label}</th>
            {models.map((m) => <th key={m} scope="col" className="num">{MODEL_NAMES[m]}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <th scope="row">
                {a.name}
                <span className="study-table__what">{a.what}</span>
              </th>
              {models.map((m) => <td key={m} className="num cmp-score"><Score c={cell(m, a.id)} /></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
      <h1 id="study-title">Does describing code to an AI help it answer questions about the code?</h1>
      <p className="lede-2">
        A program is made of functions that call one another. Questions such as “which functions end up running this one?” are hard to
        answer by reading files. This project turns a program’s source code into a database, with a written explanation of every table,
        so that an AI can answer by writing a database query. We tested whether those explanations make the AI’s answers right.
      </p>
      <div className="study-explain">
        <p><strong>What we asked.</strong> 48 questions about four real open-source Python programs, including NVIDIA’s own Auto Ontology.
          Separate AI models wrote the questions and the correct answers from the source code and the bare code database, without seeing the table descriptions or the ready-made queries, and everything was fixed in
          place before any test ran.</p>
        <p><strong>Who answered.</strong> Two AI language models, DeepSeek v4.1 Flash and NVIDIA Nemotron 3.5 Lightning: first asked
          directly, then working inside <Out href="https://github.com/NVIDIA/auto-ontology">NVIDIA Auto Ontology</Out>, NVIDIA’s system
          for answering questions about databases.</p>
        <p><strong>How we scored.</strong> An answer counts only if its query gives the right rows on the real database and also on
          eight deliberately altered copies, so a query that is right by luck on one database does not count.</p>
      </div>
      <p className="measure small">
        After the runs, a check found 21 answer keys that missed a condition stated in their own question. They were fixed before
        rescoring; no AI was asked again. <Out href={`${REPO}/study/PROTOCOL.md#corrections-after-the-runs`}>What changed</Out>,{" "}
        <Out href={`${REPO}/study/results/frozen/RESULTS.md`}>scores before the fix</Out>,{" "}
        <Out href={`${REPO}/study/RESULTS.md`}>every number</Out>.
      </p>

      <h2>An AI asked directly</h2>
      <p className="measure small">
        Questions answered correctly out of 48, averaged over five runs. Each row gives the AI more information about the database.
      </p>
      <ResultTable rows={DIRECT} models={models} cell={cell} label="The AI is given" />

      {inside.length ? (
        <>
          <h2>The same AI inside NVIDIA Auto Ontology</h2>
          <p className="measure small">
            The 12 questions about Auto Ontology’s own code, answered by Auto Ontology’s question-answering agent, averaged over three
            runs. Every row queries the same code database written by the bridge; the rows differ in what is imported on top.
          </p>
          <ResultTable rows={inside} models={models} cell={cell} label="Auto Ontology is given" />
          <p className="measure small">
            Given only the code database, Auto Ontology with DeepSeek answered 10.3 of 12 correctly. Importing the descriptions did not
            measurably add to that: 10.7 with everything is within the spread between repeat runs, and the descriptions alone scored
            8.7. For Nemotron both imports raised the score from 0.7 to 2.3. Asked directly, outside Auto Ontology, the table
            descriptions lift DeepSeek from 18.0 to 27.2 of 48.
          </p>
        </>
      ) : null}

      <h2>Question by question</h2>
      <QuestionGrid data={data} models={models} />
    </section>
  );
}

const GRID_ARMS: { id: string; short: string; name: string }[] = [
  { id: "A", short: "A", name: "asked directly, table names only" },
  { id: "B", short: "B", name: "asked directly, with table descriptions" },
  { id: "V", short: "V", name: "asked directly, with ready-made queries but no descriptions" },
  { id: "S", short: "S", name: "asked directly, with table descriptions and ready-made queries" },
  { id: "C-native", short: "AO", name: "inside Auto Ontology, code database only" },
  { id: "C-base", short: "AO+B", name: "inside Auto Ontology, with descriptions" },
  { id: "C-semantics", short: "AO+S", name: "inside Auto Ontology, with table descriptions and ready-made queries" },
];

function QuestionGrid({ data, models }: { data: StudySummary; models: string[] }) {
  const [model, setModel] = useState(models[0]);
  const [open, setOpen] = useState<string | null>(null);
  const arms = GRID_ARMS.filter((a) => data.per_question_suite_rate[`${model}/${a.id}`]);
  return (
    <>
      <div className="study-grid__head">
        <p className="measure small">
          How often each question was answered correctly, across runs. Click a question to read it in full; click a number to see
          the AI’s saved answer, with the query it wrote and the rows it got.
        </p>
        <div className="study-switch" role="group" aria-label="Model">
          {models.map((m) => (
            <button key={m} type="button" aria-pressed={m === model} onClick={() => setModel(m)}>{MODEL_NAMES[m]}</button>
          ))}
        </div>
      </div>
      <dl className="study-key">
        {GRID_ARMS.map((a) => <div key={a.id}><dt>{a.short}</dt><dd>{a.name}</dd></div>)}
      </dl>
      <div className="table-wrap">
        <table className="rows rows--compact cmp-grid study-grid">
          <thead>
            <tr>
              <th scope="col">Question</th>
              {arms.map((a) => <th key={a.id} scope="col" className="num"><abbr title={a.name}>{a.short}</abbr></th>)}
            </tr>
          </thead>
          <tbody>
            {data.question_list.map((q, i) => {
              const isOpen = open === q.id;
              const first = i === 0 || data.question_list[i - 1].repo !== q.repo;
              return [
                first ? (
                  <tr key={`${q.repo}-head`} className="study-grid__repo">
                    <th scope="colgroup" colSpan={arms.length + 1}>
                      {REPOS[q.repo]}
                      {q.repo === "auto_ontology" ? "" : " (asked directly only; Auto Ontology was tested on its own 12 questions)"}
                    </th>
                  </tr>
                ) : null,
                <tr key={q.id}>
                  <th scope="row">
                    <button type="button" className="study-grid__q" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : q.id)}>
                      {q.label ?? q.topic}
                    </button>
                  </th>
                  {arms.map((a) => {
                    const r = data.per_question_suite_rate[`${model}/${a.id}`]?.[q.id];
                    return (
                      <td key={a.id} className={`num ${r === undefined ? "" : r >= 0.5 ? "ok" : "bad"}`}>
                        {r === undefined ? "" : (
                          <a className="cmp-grid__link" href={responseUrl(model, a.id, q.repo, q.id)} target="_blank" rel="noreferrer"
                            title={`${MODEL_NAMES[model]}, ${a.name}: open the first run's response`}>{`${Math.round(r * 100)}%`}</a>
                        )}
                      </td>
                    );
                  })}
                </tr>,
                isOpen ? (
                  <tr key={`${q.id}-text`} className="study-grid__text">
                    <td colSpan={arms.length + 1}><p><span className="study-grid__id" translate="no">{q.id}, {REPOS[q.repo]}.</span> {q.question}</p></td>
                  </tr>
                ) : null,
              ];
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

// The first run's saved response for one question and configuration, on GitHub.
function responseUrl(model: string, arm: string, repo: string, qid: string): string {
  const run = arm.startsWith("C-") ? `c/${model}-${arm.slice(2)}-1` : `direct/${model}/${arm}/${repo}/r1`;
  return `${REPO}/study/runs/${run}/responses/${qid}.json`;
}
