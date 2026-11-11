// The code-semantics study (study/PROTOCOL.md): 48 blind-authored questions over four repositories,
// four ways of briefing a model, and NVIDIA Auto Ontology's own agent with and without the bridge.
// Every number comes from study/summary.json, written by study/summarise.py from the run records.

import { useEffect, useState } from "react";
import { Out } from "../components/parts";
import { FilmPair } from "../components/Films";
import { QuestionGrid } from "./StudyGrid";

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
  suite_per_repo_mean?: Record<string, number>;
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
      <div className="study-head">
      <div>
      <h1 id="study-title">Does describing code to an AI help it answer questions about the code?</h1>
      <p className="study-answer">
        Asked directly, yes: the table descriptions lift DeepSeek from 18.0 to 27.2 of 48 correct answers. Inside NVIDIA Auto Ontology,
        the code database alone already let its agent answer 10.3 of 12, and importing the descriptions did not raise that.
      </p>
      <p className="lede-2">
        A program is made of functions that call one another. Questions such as “which functions end up running this one?” are hard to
        answer by reading files. This project turns a program’s source code into a database, with a written explanation of every table,
        so that an AI can answer by writing a database query. The study tests whether those explanations make the AI’s answers right.
      </p>
      </div>
      <FilmPair compact />
      </div>
      <div className="study-explain">
        <p><strong>What was asked.</strong> 48 questions about four real open-source Python programs, including NVIDIA’s own Auto Ontology.
          Separate AI models wrote the questions and the correct answers from the source code and the bare code database, without seeing the table descriptions or the ready-made queries, and everything was fixed in
          place before any test ran.</p>
        <p><strong>Who answered.</strong> Two AI language models, DeepSeek v4.1 Flash and NVIDIA Nemotron 3.5 Lightning: first asked
          directly, then working inside <Out href="https://github.com/NVIDIA/auto-ontology">NVIDIA Auto Ontology</Out>, NVIDIA’s system
          for answering questions about databases.</p>
        <p><strong>How answers were scored.</strong> An answer counts only if its query gives the right rows on the real database and also on
          eight deliberately altered copies, so most queries that are right by luck on one database fail.</p>
      </div>
      <p className="measure small">
        After the runs, an outside reviewer and four AI auditors who saw no scores found that 21 of the 48 answer keys missed a condition
        stated in their own question. They were fixed before rescoring and no AI was asked again. The fix raised Auto Ontology’s 10.3
        from 7.3 and lowered the direct 27.2 from 34.0. <Out href={`${REPO}/study/PROTOCOL.md#corrections-after-the-runs`}>What changed</Out>,{" "}
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
            runs. Every row starts from the same code database written by the bridge; the last also adds the six ready-made queries to it.
          </p>
          <ResultTable rows={inside} models={models} cell={cell} label="Auto Ontology is given" />
          <p className="measure small">
            Given only the code database, Auto Ontology with DeepSeek answered 10.3 of 12 correctly (runs of 10, 10 and 11), and 9 of
            the 12 in every run; the same model asked directly answered 3.2. Adding the descriptions and ready-made queries gave 10.7
            (runs of 10, 12 and 10, one run answering all 12); the descriptions alone gave 8.7. For Nemotron both imports raised the
            score from 0.7 to 2.3.
          </p>
        </>
      ) : null}

      <h2>Question by question</h2>
      <QuestionGrid data={data} models={models} />
    </section>
  );
}
