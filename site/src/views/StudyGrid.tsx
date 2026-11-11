// The question-by-question grid of the code-semantics study. Every figure is a share from
// study/summary.json (per_question_suite_rate), shown as runs correct out of runs made when that
// count is exact, with links to every run's saved response on GitHub.

import "../styles/study-grid.css";
import { Fragment, useState } from "react";
import { MODEL_NAMES, type StudySummary } from "./Study";

const REPO = "https://github.com/wcook04/code-ontology-bridge/blob/main";
const QUESTIONS_URL = `${REPO}/study/questions/questions.json`;

export const GRID_ARMS: { id: string; short: string; name: string }[] = [
  { id: "A", short: "Names", name: "asked directly, table names only" },
  { id: "B", short: "+Desc", name: "asked directly, with table descriptions" },
  { id: "V", short: "+Views", name: "asked directly, with ready-made queries but no descriptions" },
  { id: "S", short: "+Both", name: "asked directly, with table descriptions and ready-made queries" },
  { id: "C-native", short: "AO", name: "inside Auto Ontology, code database only" },
  { id: "C-base", short: "AO+Desc", name: "inside Auto Ontology, with table descriptions" },
  { id: "C-semantics", short: "AO+Both", name: "inside Auto Ontology, with table descriptions and ready-made queries" },
];

export const REPOS: Record<string, string> = { auto_ontology: "NVIDIA Auto Ontology", click: "pallets/click", httpx: "encode/httpx", rich: "Textualize/rich" };

// One run's saved response for one question and configuration, on GitHub (run 1 by default).
export function responseUrl(model: string, arm: string, repo: string, qid: string, run = 1): string {
  const dir = arm.startsWith("C-") ? `c/${model}-${arm.slice(2)}-${run}` : `direct/${model}/${arm}/${repo}/r${run}`;
  return `${REPO}/study/runs/${dir}/responses/${qid}.json`;
}

type Filter = "all" | "ao" | "wrong";

const pct = (r: number) => `${Math.round(r * 100)}%`;

// Runs correct, when the share times the number of runs is a whole number; otherwise null.
function runsCorrect(r: number, n: number): number | null {
  const k = Math.round(r * n);
  return n > 0 && Math.abs(r * n - k) < 1e-6 ? k : null;
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function QuestionGrid({ data, models }: { data: StudySummary; models: string[] }) {
  const [model, setModel] = useState(models[0]);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);

  const rates = (arm: string) => data.per_question_suite_rate[`${model}/${arm}`];
  const arms = GRID_ARMS.filter((a) => rates(a.id));
  const reps = (arm: string) => data.cells.find((c) => c.model === model && c.arm === arm)?.repetitions ?? 0;

  const all = data.question_list;
  const aoCount = all.filter((q) => q.repo === "auto_ontology").length;
  const hasWrong = (qid: string) => arms.some((a) => {
    const r = rates(a.id)?.[qid];
    return r !== undefined && r < 1 - 1e-9;
  });
  const shown = all.filter((q) => (filter === "ao" ? q.repo === "auto_ontology" : filter === "wrong" ? hasWrong(q.id) : true));
  const wrongCount = all.filter((q) => hasWrong(q.id)).length;

  const filters: { id: Filter; label: string }[] = [
    { id: "all", label: `All ${all.length} questions` },
    { id: "ao", label: `The ${aoCount} Auto Ontology questions` },
    { id: "wrong", label: "Questions with a wrong answer from this model" },
  ];

  const countLine =
    filter === "wrong"
      ? `Showing ${shown.length} of ${all.length} questions: the ${wrongCount} with at least one wrong answer from ${MODEL_NAMES[model]}.`
      : `Showing ${shown.length} of ${all.length} questions.`;

  const cols = arms.length + 1;

  return (
    <div className="sg">
      <div className="study-grid__head sg-head">
        <p className="measure small">
          Each figure is the number of runs that answered a question correctly, out of the runs made, and links to the first run’s
          saved answer, with the query it wrote and the rows it got. A ✕ marks a figure where most runs were wrong. A question’s row opens
          its full wording and every saved answer.
        </p>
        <div className="sg-controls">
          <div className="study-switch sg-switch" role="group" aria-label="Model">
            {models.map((m) => (
              <button key={m} type="button" aria-pressed={m === model} onClick={() => setModel(m)}>{MODEL_NAMES[m]}</button>
            ))}
          </div>
          <div className="study-switch sg-switch" role="group" aria-label="Questions shown">
            {filters.map((f) => (
              <button key={f.id} type="button" aria-pressed={f.id === filter} onClick={() => setFilter(f.id)}>{f.label}</button>
            ))}
          </div>
        </div>
      </div>
      <dl className="study-key">
        {GRID_ARMS.map((a) => <div key={a.id}><dt>{a.short}</dt><dd>{a.name}</dd></div>)}
      </dl>
      <p className="sg-count small" aria-live="polite">{countLine}</p>
      <div className="table-wrap sg-wrap" role="region" aria-label="Question-by-question results" tabIndex={0}>
        <table className="rows rows--compact cmp-grid study-grid sg-table">
          <thead>
            <tr>
              <th scope="col" className="sg-qcol">Question</th>
              {arms.map((a) => <th key={a.id} scope="col" className="num"><abbr title={a.name}>{a.short}</abbr></th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((q, i) => {
              const isOpen = open === q.id;
              const first = i === 0 || shown[i - 1].repo !== q.repo;
              const detailId = `sg-detail-${q.id}`;
              const ran = arms.filter((a) => rates(a.id)?.[q.id] !== undefined);
              return (
                <Fragment key={q.id}>
                  {first ? (
                    <tr className="study-grid__repo sg-repo">
                      <th scope="colgroup" colSpan={cols}>
                        <span className="sg-pin">
                          {REPOS[q.repo]}
                          {q.repo === "auto_ontology" ? "" : " (asked directly only; Auto Ontology was tested on its own 12 questions)"}
                        </span>
                      </th>
                    </tr>
                  ) : null}
                  <tr className={isOpen ? "sg-row is-open" : "sg-row"}>
                    <th scope="row" className="sg-qcol">
                      <button type="button" className="study-grid__q sg-q" aria-expanded={isOpen} aria-controls={isOpen ? detailId : undefined}
                        onClick={() => setOpen(isOpen ? null : q.id)}>
                        {q.label ?? q.topic}
                      </button>
                    </th>
                    {arms.map((a) => {
                      const r = rates(a.id)?.[q.id];
                      if (r === undefined) return <td key={a.id} className="num" />;
                      const n = reps(a.id);
                      const k = runsCorrect(r, n);
                      const bad = r < 0.5;
                      const said = `${k === null ? pct(r) : `${k} of ${n} runs correct, ${pct(r)}`}${bad ? ", wrong in most runs" : ""}`;
                      return (
                        <td key={a.id} className={`num sg-cell ${bad ? "bad" : "ok"}`}>
                          <a className="cmp-grid__link sg-link" href={responseUrl(model, a.id, q.repo, q.id)} target="_blank" rel="noreferrer"
                            title={`${MODEL_NAMES[model]}, ${a.name}: ${said}. Links to the first run’s saved answer.`}
                            aria-label={`${a.short}: ${said}. First run’s saved answer, on GitHub`}>
                            {bad ? <span className="sg-mark" aria-hidden="true">✕</span> : null}
                            {k === null ? pct(r) : <>{k}<span className="sg-of">/</span>{n}</>}
                          </a>
                        </td>
                      );
                    })}
                  </tr>
                  {isOpen ? (
                    <tr className="study-grid__text sg-detail-row">
                      <td colSpan={cols}>
                        <div className="sg-detail" id={detailId}>
                          <p className="sg-detail__id">
                            <span translate="no">{q.id}</span>, {REPOS[q.repo]}
                          </p>
                          <dl className="sg-detail__facts">
                            <div><dt>Topic</dt><dd>{q.topic}</dd></div>
                            <div><dt>Difficulty</dt><dd>{q.difficulty}</dd></div>
                          </dl>
                          <p className="sg-detail__question">{q.question}</p>
                          <h3 className="sg-detail__head">Saved answers from {MODEL_NAMES[model]}</h3>
                          <ul className="sg-runs">
                            {ran.map((a) => {
                              const r = rates(a.id)![q.id];
                              const n = reps(a.id);
                              const k = runsCorrect(r, n);
                              return (
                                <li key={a.id}>
                                  <span className="sg-runs__name">{capital(a.name)}</span>
                                  <span className="sg-runs__score">{k === null ? `${pct(r)} of runs correct` : `${k} of ${n} runs correct`}</span>
                                  <span className="sg-runs__links">
                                    {Array.from({ length: n }, (_, j) => (
                                      <a key={j} href={responseUrl(model, a.id, q.repo, q.id, j + 1)} target="_blank" rel="noreferrer"
                                        aria-label={`Run ${j + 1}, ${a.name}: saved answer on GitHub`}>
                                        run {j + 1}
                                      </a>
                                    ))}
                                  </span>
                                </li>
                              );
                            })}
                          </ul>
                          <p className="sg-detail__note">
                            The results summary records how many runs were correct, not which ones; each saved answer holds the query that
                            run wrote and the rows it returned.{" "}
                            <a href={QUESTIONS_URL} target="_blank" rel="noreferrer">All {all.length} questions with their answer keys, on GitHub</a>
                            {" "}(this one is <span translate="no">{q.id}</span>).
                          </p>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
