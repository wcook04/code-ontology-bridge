// All 22 recorded outcomes. Filtering happens in the browser over the published
// list; the run’s totals always describe the complete run, never the filtered view.

import { useEffect, useRef, useState } from "react";
import type { Outcomes as OutcomeList } from "../data/types";
import { useRoute } from "../data/useRoute";
import { Gate, ProseStatus, TableStatus } from "../components/parts";
import { entryState, href, onLinkClick, replaceView } from "../app/router";

const OUTCOMES = "/api/v1/outcomes?limit=100";
type TableFilter = "" | "pass" | "fail";
type ProseFilter = "" | "substantive" | "fail" | "unknown";

export function Outcomes({ params }: { params: URLSearchParams }) {
  const outcomes = useRoute<OutcomeList>(OUTCOMES);
  return (
    <section className="band page" aria-labelledby="outcomes-title">
      <h1 id="outcomes-title">All 22 recorded questions</h1>
      <Gate loaded={outcomes} what="the outcome list">
        {(o) => <OutcomeTable o={o} params={params} />}
      </Gate>
    </section>
  );
}

function OutcomeTable({ o, params }: { o: OutcomeList; params: URLSearchParams }) {
  const [q, setQ] = useState(params.get("q") ?? "");
  const [table, setTable] = useState<TableFilter>((params.get("table") as TableFilter) ?? "");
  const [prose, setProse] = useState<ProseFilter>((params.get("prose") as ProseFilter) ?? "");
  const restored = useRef(false);

  useEffect(() => {
    const next = new URLSearchParams();
    if (q) next.set("q", q);
    if (table) next.set("table", table);
    if (prose) next.set("prose", prose);
    replaceView({}, href({ view: "outcomes", params: next }));
  }, [q, table, prose]);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    const y = entryState().scrollY;
    if (y !== undefined) window.scrollTo(0, y);
  }, []);

  const needle = q.trim().toLowerCase();
  const items = o.items.filter(
    (i) =>
      (!table || i.assessment.table_match === table) &&
      (!prose || i.assessment.prose_review === prose) &&
      (!needle || String(i.question_id) === needle.replace(/^q/, "") || i.question.toLowerCase().includes(needle)),
  );
  const pc = o.population_counts;

  return (
    <>
      <p className="lede-2">
        Each question was asked of Auto Ontology over the bridge’s export of its own repository. Two judgments are recorded separately: a
        program checked whether the returned rows matched the reference rows, and the author read the written answer.
      </p>
      <dl className="totals">
        <div>
          <dt>Rows matched the reference</dt>
          <dd>
            {pc.table_match.pass ?? 0} of {o.population_total}
          </dd>
        </div>
        <div>
          <dt>Written answer judged substantive</dt>
          <dd>
            {pc.prose_review.substantive ?? 0} of {o.population_total}
            <span className="small muted">
              {" "}
              ({pc.prose_review.fail ?? 0} failed, {pc.prose_review.unknown ?? 0} not classified)
            </span>
          </dd>
        </div>
      </dl>
      <p className="small muted measure">{o.scope} The author’s prose review was not blinded.</p>

      <div className="filters" role="search">
        <label className="field">
          <span>Search questions</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Words or a number, e.g. caller or 14" />
        </label>
        <label className="field">
          <span>Table check</span>
          <select value={table} onChange={(e) => setTable(e.target.value as TableFilter)}>
            <option value="">Any</option>
            <option value="pass">Rows matched</option>
            <option value="fail">Rows did not match</option>
          </select>
        </label>
        <label className="field">
          <span>Prose review</span>
          <select value={prose} onChange={(e) => setProse(e.target.value as ProseFilter)}>
            <option value="">Any</option>
            <option value="substantive">Substantive</option>
            <option value="fail">Prose failed</option>
            <option value="unknown">Not classified</option>
          </select>
        </label>
      </div>
      <p className="showing" role="status">
        Showing {items.length} of {o.population_total} questions
        {table || prose || needle ? ". Totals above still describe the whole run." : "."}
        {table || prose || needle ? (
          <>
            {" "}
            <button type="button" className="link-button" onClick={() => { setQ(""); setTable(""); setProse(""); }}>
              Clear filters
            </button>
          </>
        ) : null}
      </p>
      <div className="table-wrap">
        <table className="rows outcomes">
          <caption className="visually-hidden">Recorded questions with their two assessments</caption>
          <thead>
            <tr>
              <th scope="col" className="num">
                No.
              </th>
              <th scope="col">Question</th>
              <th scope="col">Table check</th>
              <th scope="col">Prose review</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.question_id}>
                <td className="num">{i.question_id}</td>
                <td>
                  <a href={href({ view: "question", id: i.question_id })} onClick={onLinkClick}>
                    {i.question}
                  </a>
                  {i.question_id === 11 ? <span className="tag">, the example on the front page</span> : null}
                  {i.review_finding ? <span className="small muted outcomes__finding">{i.review_finding.reason}</span> : null}
                </td>
                <td>
                  <TableStatus value={i.assessment.table_match} />
                </td>
                <td>
                  <ProseStatus value={i.assessment.prose_review} />
                </td>
              </tr>
            ))}
            {items.length === 0 ? (
              <tr>
                <td colSpan={4} className="rows__empty">
                  No question matches these filters.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </>
  );
}
