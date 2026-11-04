// All 22 recorded questions: each one's result in a sentence, and how Auto
// Ontology did. Totals always describe the whole run, never the filtered view.

import { useEffect, useRef, useState } from "react";
import type { Outcomes as OutcomeList, QuestionDetail } from "../data/types";
import { useRoute } from "../data/useRoute";
import { readRoute } from "../data/client";
import { Gate } from "../components/parts";
import { entryState, href, onLinkClick, replaceView } from "../app/router";
import { FINDINGS, proseReading } from "../app/findings";

const OUTCOMES = "/api/v1/outcomes?limit=100";
type RowsFilter = "" | "pass" | "fail";

function useDetails(ids: number[]): Record<number, QuestionDetail> {
  const [details, setDetails] = useState<Record<number, QuestionDetail>>({});
  const key = ids.join(",");
  useEffect(() => {
    let live = true;
    for (const id of ids) {
      readRoute<QuestionDetail>(`/api/v1/questions/${id}`).then(
        (d) => live && setDetails((all) => ({ ...all, [id]: d })),
        () => undefined,
      );
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return details;
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
  const details = useDetails(o.items.map((i) => i.question_id));

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
          <dt>The SQL returned exactly the expected rows</dt>
          <dd>
            {pass} of {o.population_total}
          </dd>
        </div>
        <div>
          <dt>The written answer states the result</dt>
          <dd>0 of {o.population_total}</dd>
        </div>
      </dl>
      <p className="measure">
        Question 14’s written answer is the single word “thought”. The other 21 describe the query Auto Ontology ran rather than what it
        found. The author’s recorded review counted 20 of those as substantive explanations of the SQL. The one-line results below were written for
        this website from the returned rows.
      </p>
      <p className="small muted measure">
        One run, on questions written during development, with no held-out questions and no comparison against an agent given the database
        without the semantic model.
      </p>

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
          const f = FINDINGS[i.question_id];
          const d = details[i.question_id];
          const rows = d?.result_tables[0] ?? [];
          const prose = d ? proseReading(d.answer) : null;
          return (
            <li key={i.question_id} className="qlist__item">
              <span className="qlist__n">{i.question_id}</span>
              <div className="qlist__body">
                <a className="qlist__title" href={href({ view: "question", id: i.question_id })} onClick={onLinkClick}>
                  {f?.title ?? i.question}
                </a>
                <p className="qlist__says">{d && f ? f.says(rows) : " "}</p>
                <p className="qlist__status">
                  <span className={i.assessment.table_match === "pass" ? "ok" : "bad"}>
                    {i.assessment.table_match === "pass" ? "✓ Expected rows" : "✕ Wrong rows"}
                  </span>
                  {prose?.tone === "fail" ? <span className="bad">✕ Written answer is one word</span> : null}
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
