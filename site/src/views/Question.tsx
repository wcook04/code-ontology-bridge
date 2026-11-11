// One recorded question, in the order a reader needs it: the question, what
// the returned rows show, how Auto Ontology did, then the evidence on demand.

import { useEffect, useState } from "react";
import type { QuestionDetail } from "../data/types";
import { useRoute } from "../data/useRoute";
import { Captured, Gate, Out, RowsTable } from "../components/parts";
import { ResultView } from "../components/ResultView";
import { RequestBlock, Results } from "../components/Evidence";
import { entryState, href, onLinkClick } from "../app/router";
import { ATTEMPTS, ELAPSED, PROSE_REVIEW_WORDS, findingFor, proseReading } from "../app/findings";
import { readableSql } from "../app/sql";

const REPO = "https://github.com/wcook04/code-ontology-bridge/blob/main/examples/auto-ontology/live/current/";

export function Question({ id, total }: { id: number; total: number }) {
  const loaded = useRoute<QuestionDetail>(`/api/v1/questions/${id}`);
  useEffect(() => {
    if (loaded.state !== "ready") return;
    window.scrollTo(0, entryState().scrollY ?? 0);
  }, [loaded.state, id]);
  return (
    <article className="band page question" aria-labelledby="q-title">
      <nav className="crumbs" aria-label="Breadcrumb">
        <a href="#/outcomes" onClick={onLinkClick}>
          ← All 22 questions
        </a>
      </nav>
      <Gate loaded={loaded} what={`question ${id}`}>
        {(q) => <Body q={q} total={total} />}
      </Gate>
    </article>
  );
}

function Body({ q, total }: { q: QuestionDetail; total: number }) {
  const f = findingFor(q.question_id, q.output_contract.fields.map((x) => x.name));
  const links = Object.fromEntries(q.display_annotations.links.filter((l) => l.table_index === 0).map((l) => [`${l.row_index}:${l.column}`, l.source_url]));
  const rows = q.result_tables[0] ?? [];
  const prose = proseReading(q.answer);
  const rowsOk = q.assessment.table_match === "pass";
  return (
    <>
      <p className="kicker">
        Question {q.question_id} of {total}
        {f ? `, ${f.kind.toLowerCase()}` : ""}
      </p>
      <h1 id="q-title">{f?.title ?? q.question}</h1>
      {f && f.title !== q.question ? <p className="asked">Asked as: “{q.question}”</p> : null}

      <section className="finding" aria-labelledby="finding-title">
        <h2 id="finding-title" className="visually-hidden">What is in the returned rows</h2>
        {f ? <p className="finding__says">{f.says(rows)}</p> : null}
        {f ? <ResultView finding={f} rows={rows} contract={q.output_contract} referenceText={q.reference_rows} links={links} /> : <p className="notice">This question’s columns differ from the ones this website’s summary was written for, so no summary is shown. The recorded rows are under “The recorded evidence”.</p>}
        {f?.limit ? <p className="finding__limit">{f.limit}</p> : null}
        <p className="finding__source">This summary was written for this website from the {rows.length} recorded {rows.length === 1 ? "row" : "rows"}. It is not Auto Ontology’s answer.</p>
      </section>

      <section className="verdict" aria-labelledby="verdict-title">
        <h2 id="verdict-title">How Auto Ontology did</h2>
        <div className="verdict__grid">
          <div className={`verdict__item ${rowsOk ? "is-pass" : "is-fail"}`}>
            <p className="verdict__head">{rowsOk ? "✓ The SQL returned exactly the expected rows" : "✕ The SQL returned the wrong rows"}</p>
            <p className="small">
              {q.score.agent_rows} returned, {q.score.reference_rows} expected
              {q.output_contract.ordered ? (q.score.order_matches ? ", in the expected order" : ", in a different order") : ""}. A program compared them with
              rows from a reference query the author wrote.
            </p>
            {ATTEMPTS[q.question_id] ? (
              <p className="small muted">
                {ATTEMPTS[q.question_id].runs === 1
                  ? "The first SQL it ran gave these rows."
                  : ATTEMPTS[q.question_id].schemaError
                    ? "Its first query named a table without its “code.” schema and failed; Auto Ontology rewrote it, and the second run gave these rows."
                    : `Auto Ontology rewrote the query ${ATTEMPTS[q.question_id].rewrites} times after checking it; it ran ${ATTEMPTS[q.question_id].runs} times.`}
              </p>
            ) : null}
            {ELAPSED[q.question_id] ? <p className="small muted">The request took {Math.round(ELAPSED[q.question_id])} seconds, with three requests running at a time.</p> : null}
            {q.review_finding && !rowsOk ? <p className="small">{q.review_finding.reason}</p> : null}
          </div>
          <div className={`verdict__item is-${prose.tone}`}>
            <p className="verdict__head">{prose.tone === "fail" ? "✕ " : ""}{prose.label}</p>
            <blockquote className="verdict__quote">{q.answer}</blockquote>
            <p className="small muted">
              Auto Ontology’s written response, verbatim. Its agent writes this together with the SQL, before the query runs, to describe
              the calculation; the rows are returned beside it.
            </p>
            {q.assessment.review_method === "not_supplied" ? null : <p className="small">{PROSE_REVIEW_WORDS[q.assessment.prose_review] ?? ""}</p>}
          </div>
        </div>
        {f?.sqlNote ? <p className="small measure">{f.sqlNote}</p> : null}
      </section>

      <section className="evidence" aria-labelledby="evidence-title">
        <h2 id="evidence-title">The recorded evidence</h2>
        <Fold title="The SQL Auto Ontology wrote" open>
          <SqlBlock sql={q.sql} />
        </Fold>
        <Fold title={rowsOk ? "Returned rows next to the reference rows" : "Returned rows next to the reference rows (they differ)"} open={!rowsOk}>
          <Results tables={q.result_tables} referenceText={q.reference_rows} contract={q.output_contract} score={q.score} />
        </Fold>
        <Fold title="The reference SQL used for scoring">
          <Captured className="sql" text={q.reference_sql} label="Reference SQL" />
          <p className="small muted">Written by the author with the question. It was not part of the request.</p>
        </Fold>
        <Fold title="The question exactly as submitted, with its hint">
          <RequestBlock request={q.request} contract={q.output_contract} />
        </Fold>
        <Fold title="Recorded file and score">
          <p className="small">
            <Out href={REPO + q.artifact}>{q.artifact}</Out>
          </p>
          <p className="small muted">SHA-256 {q.sha256}</p>
          <RowsTable
            rows={[q.score as unknown as Record<string, unknown>]}
            columns={["agent_rows", "reference_rows", "strict_rows_pass", "values_match", "order_matches", "schema_complete"]}
            caption="Automatic score"
          />
        </Fold>
      </section>

      <nav className="pager" aria-label="Other questions">
        {q.question_id > 1 ? (
          <a href={href({ view: "question", id: q.question_id - 1 })} onClick={onLinkClick}>
            ← Question {q.question_id - 1}
          </a>
        ) : (
          <span />
        )}
        {q.question_id < total ? (
          <a href={href({ view: "question", id: q.question_id + 1 })} onClick={onLinkClick}>
            Question {q.question_id + 1} →
          </a>
        ) : null}
      </nav>
    </>
  );
}

function Fold({ title, open, children }: { title: string; open?: boolean; children: React.ReactNode }) {
  return (
    <details className="evidence__fold" open={open}>
      <summary>{title}</summary>
      <div className="evidence__body">{children}</div>
    </details>
  );
}

export function SqlBlock({ sql }: { sql: string }) {
  const [exact, setExact] = useState(false);
  const single = !sql.includes("\n");
  return (
    <div className="sqlblock">
      <Captured className="sql sql--wide" text={exact ? sql : readableSql(sql)} label="Generated SQL" />
      {single ? (
        <p className="small muted">
          {exact ? "Shown exactly as captured, on one line." : "Line breaks added before each clause for reading; nothing else changed."}{" "}
          <button type="button" className="btn-quiet" onClick={() => setExact(!exact)}>
            {exact ? "Add line breaks" : "Show exactly as captured"}
          </button>
        </p>
      ) : null}
    </div>
  );
}
