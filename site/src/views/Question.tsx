// One recorded question: the same inspection for a success or a failure.

import { useEffect } from "react";
import type { QuestionDetail } from "../data/types";
import { useRoute } from "../data/useRoute";
import { Captured, Gate, Out } from "../components/parts";
import { AnswerProse, AssessmentBlock, RequestBlock, Results, SqlPair } from "../components/Evidence";
import { back, entryState, href, onLinkClick } from "../app/router";

const REPO = "https://github.com/wcook04/code-ontology-bridge/blob/main/examples/auto-ontology/live/current/";

export function Question({ id, total }: { id: number; total: number }) {
  const loaded = useRoute<QuestionDetail>(`/api/v1/questions/${id}`);
  useEffect(() => {
    if (loaded.state !== "ready") return;
    const y = entryState().scrollY;
    window.scrollTo(0, y ?? 0);
  }, [loaded.state, id]);
  return (
    <article className="band page" aria-labelledby="q-title">
      <nav className="crumbs" aria-label="Back">
        <button type="button" className="link-button" onClick={() => back("#/outcomes")}>
          ← Back
        </button>
        <a href="#/outcomes" onClick={onLinkClick}>
          All 22 questions
        </a>
      </nav>
      <Gate loaded={loaded} what={`question ${id}`}>
        {(q) => (
          <>
            <p className="kicker">Question {q.question_id} of {total}</p>
            <h1 id="q-title">{q.question}</h1>
            {q.question_id === 11 ? (
              <p className="small">
                This is the question the <a href="#/" onClick={onLinkClick}>caller example</a> walks through.
              </p>
            ) : null}
            <AssessmentBlock assessment={q.assessment} score={q.score} finding={q.review_finding} />
            <h2>Request</h2>
            <RequestBlock request={q.request} contract={q.output_contract} />
            <h2>SQL</h2>
            <SqlPair sql={q.sql} reference={q.reference_sql} />
            <h2>Rows</h2>
            <Results tables={q.result_tables} referenceText={q.reference_rows} contract={q.output_contract} score={q.score} />
            <h2>Written answer</h2>
            <AnswerProse text={q.answer} />
            {q.display_annotations.links.length ? (
              <>
                <h3>Source links for returned identifiers</h3>
                <p className="small muted">{q.display_annotations.note}</p>
                <ul className="links-list">
                  {q.display_annotations.links.map((l) => (
                    <li key={`${l.table_index}-${l.row_index}-${l.column}`}>
                      <Out href={l.source_url}>
                        <code className="wrap-id">{l.identity}</code>
                      </Out>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
            <h2>Recorded file</h2>
            <p className="small">
              <Out href={REPO + q.artifact}>{q.artifact}</Out>, SHA-256 <code className="wrap-id">{q.sha256}</code>
            </p>
            <details className="fold">
              <summary>Show the complete score record</summary>
              <Captured text={JSON.stringify(q.score, null, 2)} />
            </details>
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
        )}
      </Gate>
    </article>
  );
}
