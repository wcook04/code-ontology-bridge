// All 22 recorded questions: each one's result in a sentence, and how Auto
// Ontology did. Totals always describe the whole run, never the filtered view.

import { useEffect, useRef, useState } from "react";
import type { Outcomes as OutcomeList, QuestionDetail } from "../data/types";
import { useRoute } from "../data/useRoute";
import { readRoute } from "../data/client";
import { Gate } from "../components/parts";
import { RunConfig } from "../components/RunConfig";
import { entryState, href, onLinkClick, replaceView } from "../app/router";
import { FINDINGS, findingFor, proseReading } from "../app/findings";

const OUTCOMES = "/api/v1/outcomes?limit=100";
type RowsFilter = "" | "pass" | "fail";

function useDetails(ids: number[]): { details: Record<number, QuestionDetail | "error">; retry: () => void } {
  const [details, setDetails] = useState<Record<number, QuestionDetail | "error">>({});
  const [attempt, setAttempt] = useState(0);
  const key = ids.join(",");
  useEffect(() => {
    let live = true;
    for (const id of ids) {
      readRoute<QuestionDetail>(`/api/v1/questions/${id}`).then(
        (d) => live && setDetails((all) => ({ ...all, [id]: d })),
        () => live && setDetails((all) => ({ ...all, [id]: "error" })),
      );
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);
  return { details, retry: () => setAttempt((n) => n + 1) };
}

export function Outcomes({ params }: { params: URLSearchParams }) {
  const outcomes = useRoute<OutcomeList>(OUTCOMES);
  return (
    <section className="band page" aria-labelledby="outcomes-title">
      <h1 id="outcomes-title">The 22 recorded questions</h1>
      <Gate loaded={outcomes} what="the outcome list">
        {(o) => <OutcomeTable o={o} params={params} />}
      </Gate>
    </section>
  );
}

function OutcomeTable({ o, params }: { o: OutcomeList; params: URLSearchParams }) {
  const [q, setQ] = useState(params.get("q") ?? "");
  const [rowsFilter, setRowsFilter] = useState<RowsFilter>((params.get("rows") as RowsFilter) ?? "");
  const restored = useRef(false);
  const { details, retry } = useDetails(o.items.map((i) => i.question_id));

  useEffect(() => {
    const next = new URLSearchParams();
    if (q) next.set("q", q);
    if (rowsFilter) next.set("rows", rowsFilter);
    replaceView({}, href({ view: "outcomes", params: next }));
  }, [q, rowsFilter]);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const y = entryState().scrollY;
    if (y !== undefined) window.scrollTo(0, y);
  }, []);

  const needle = q.trim().toLowerCase();
  const items = o.items.filter((i) => {
    const f = FINDINGS[i.question_id];
    const text = `${i.question} ${f?.title ?? ""} ${f?.kind ?? ""}`.toLowerCase();
    return (!rowsFilter || i.assessment.table_match === rowsFilter) && (!needle || String(i.question_id) === needle.replace(/^q/, "") || text.includes(needle));
  });
  const pass = o.population_counts.table_match.pass ?? 0;

  return (
    <>
      <p className="lede-2">
        The author wrote these questions while building the project and asked each one of Auto Ontology over the extracted database of
        Auto Ontology’s own code. Each request named the columns to return, and most came with a hint on how to answer.
      </p>
      <dl className="totals">
        <div>
          <dt>Returned exactly the expected rows</dt>
          <dd>
            {pass} of {o.population_total}
          </dd>
        </div>
        <div>
          <dt>Expected rows and an explanation of the query</dt>
          <dd>20 of {o.population_total}</dd>
        </div>
        <div>
          <dt>Median time per request</dt>
          <dd>146 s</dd>
        </div>
      </dl>
      <p className="measure">
        Each response has two parts: the rows the SQL returned, and a short written explanation of the query. Auto Ontology’s agent writes
        that explanation together with the SQL, before the query runs, so it describes the calculation rather than the result. Question 2
        returned an extra row; question 14’s explanation is the single word “thought”.
      </p>
      <RunConfig />
      <div className="filters" role="search">
        <label className="field">
          <span>Search</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. imports, callers or 14" />
        </label>
        <label className="field">
          <span>Rows</span>
          <select value={rowsFilter} onChange={(e) => setRowsFilter(e.target.value as RowsFilter)}>
            <option value="">All questions</option>
            <option value="pass">Exactly the expected rows</option>
            <option value="fail">Wrong rows</option>
          </select>
        </label>
      </div>
      <p className="showing" role="status">
        Showing {items.length} of {o.population_total}.
        {q || rowsFilter ? (
          <>
            {" "}
            <button type="button" className="link-button" onClick={() => { setQ(""); setRowsFilter(""); }}>
              Show all
            </button>
          </>
        ) : null}
      </p>
      <ol className="qlist">
        {items.map((i) => {
          const loaded = details[i.question_id];
          const d = loaded && loaded !== "error" ? loaded : undefined;
          const f = d ? findingFor(i.question_id, d.output_contract.fields.map((x) => x.name)) : FINDINGS[i.question_id];
          const rows = d?.result_tables[0] ?? [];
          const prose = d ? proseReading(d.answer) : null;
          return (
            <li key={i.question_id} className="qlist__item">
              <span className="qlist__n">{i.question_id}</span>
              <div className="qlist__body">
                <a className="qlist__title" href={href({ view: "question", id: i.question_id })} onClick={onLinkClick}>
                  {f?.title ?? i.question}
                </a>
                {loaded === "error" ? (
                  <p className="qlist__says bad">
                    This question’s record could not be loaded.{" "}
                    <button type="button" className="link-button" onClick={retry}>
                      Try again
                    </button>
                  </p>
                ) : (
                  <p className="qlist__says">{d && f ? f.says(rows) : d ? "See the recorded rows." : " "}</p>
                )}
                <p className="qlist__status">
                  <span className={i.assessment.table_match === "pass" ? "ok" : "bad"}>
                    {i.assessment.table_match === "pass" ? "✓ Expected rows" : "✕ Wrong rows"}
                  </span>
                  {prose?.tone === "fail" ? <span className="bad">✕ Explanation is one word</span> : null}
                  {i.question_id === 11 ? (
                    <a href="#/walkthrough/source" onClick={onLinkClick}>
                      Followed step by step on the front page
                    </a>
                  ) : null}
                </p>
              </div>
            </li>
          );
        })}
        {items.length === 0 ? <li className="qlist__empty">No question matches.</li> : null}
      </ol>
    </>
  );
}
