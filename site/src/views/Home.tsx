// The front page: what the project does, drawn, then one recorded question
// followed in five steps from a line of Python to the rows Auto Ontology
// returned. Prose uses plain names; the exact identifiers are in glossary cards.

import { useEffect, useState } from "react";
import type { AnswerStep, ModelStep, Outcomes, RecordsStep, RequestStep, SourceStep, SqlStep, Term as ModelTerm, Walkthrough } from "../data/types";
import { useRoute } from "../data/useRoute";
import { CallerGraph, type Selection } from "../components/CallerGraph";
import { SystemDiagram } from "../components/SystemDiagram";
import { Term } from "../components/Term";
import { CopyButton, Excerpt, Gate, Out, ProseStatus, TableStatus } from "../components/parts";
import { AnswerProse, AssessmentBlock, RequestBlock, Results, SqlPair } from "../components/Evidence";
import { entryState, href, onLinkClick, replaceView } from "../app/router";
import { ROLES, roleOf } from "../app/roles";
import { termForSymbol } from "../app/glossary";

const WALKTHROUGH = "/api/v1/walkthroughs/caller-chain-q11";
const OUTCOMES = "/api/v1/outcomes?limit=100";
const CALLBACK_ID = "auto_ontology/ingestion_service/semantic_scheduler.py:203:24:0";
const SCHEDULER = "auto_ontology/ingestion_service/semantic_scheduler.py::SemanticScheduler._run_once";
const ALIASES: Record<string, string> = { sql: "request", model: "records" };

function step<T>(w: Walkthrough, id: string): T {
  const found = w.steps.find((s) => s.id === id);
  if (!found) throw new Error(`The walkthrough has no ${id} step.`);
  return found.data as T;
}

/** A symbol by its plain role name, with its glossary card. */
function Sym({ id, lower }: { id: string; lower?: boolean }) {
  const role = roleOf(id);
  const label = lower ? `the ${role.toLowerCase()}` : role;
  const term = termForSymbol(id);
  return term ? <Term id={term}>{label}</Term> : <>{label}</>;
}

export function Home({ stepTarget }: { stepTarget?: string }) {
  const walkthrough = useRoute<Walkthrough>(WALKTHROUGH);
  return (
    <>
      <Hero />
      <Gate loaded={walkthrough} what="the recorded example">
        {(w) => <Example w={w} stepTarget={stepTarget} />}
      </Gate>
    </>
  );
}

function Hero() {
  return (
    <section className="hero band" aria-labelledby="hero-title">
      <h1 id="hero-title">Ask NVIDIA’s database agent questions about Python code</h1>
      <p className="lede">
        <Term id="auto-ontology">NVIDIA Auto Ontology</Term> lets you ask a database questions in English: its agent writes SQL, runs it and
        answers. This project turns a Python repository into the two inputs Auto Ontology already accepts, a database of the code’s files,
        functions and calls, and a <Term id="semantic-model">semantic model</Term> that says what each table means.
      </p>
      <SystemDiagram onOpen={jump} />
      <div className="actions">
        <a className="btn" href={href({ view: "home", step: "source" })} onClick={(e) => { e.preventDefault(); jump("source"); }}>
          Follow one question from code to answer
        </a>
        <a className="btn-ghost" href="#/outcomes" onClick={onLinkClick}>
          See all 22 recorded questions
        </a>
      </div>
    </section>
  );
}

function jump(id: string): void {
  const target = ALIASES[id] ?? id;
  const el = document.getElementById(`step-${target}`);
  if (!el) return;
  replaceView({}, href({ view: "home", step: target }));
  el.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  el.focus({ preventScroll: true });
}

function Example({ w, stepTarget }: { w: Walkthrough; stepTarget?: string }) {
  const source = step<SourceStep>(w, "source");
  const records = step<RecordsStep>(w, "records");
  const model = step<ModelStep>(w, "model");
  const request = step<RequestStep>(w, "request");
  const sql = step<SqlStep>(w, "sql");
  const answer = step<AnswerStep>(w, "answer");

  useEffect(() => {
    const saved = entryState().scrollY;
    if (saved !== undefined) window.scrollTo(0, saved);
    else if (stepTarget) document.getElementById(`step-${ALIASES[stepTarget] ?? stepTarget}`)?.scrollIntoView({ block: "start" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <section className="band walk-intro" aria-labelledby="walk-title">
        <h2 id="walk-title">The test: Auto Ontology’s own code</h2>
        <p className="lede-2">
          The extractor was run on Auto Ontology’s own repository, {w.snapshot.file_count} Python files, and Auto Ontology was then asked 22
          questions about that code. Question {w.question_id} asked: if the function <Term id="resolver">resolve_semantic_fks</Term> changed,
          which other functions would be affected? Auto Ontology found four. One of them, <Sym id={SCHEDULER} lower />, never calls any of the
          others. The five steps below show how it was found anyway.
        </p>
        <p className="small muted measure">
          Everything on this page was recorded during one run of Auto Ontology at a fixed revision; the website itself runs no model and no SQL.
          That run needed a small compatibility patch to Auto Ontology, described in the{" "}
          <Out href="https://github.com/wcook04/code-ontology-bridge/blob/main/docs/reproduction.md">reproduction guide</Out>.
        </p>
      </section>

      <SourcePart source={source} />
      <TablesPart records={records} model={model} />
      <GraphPart records={records} />
      <section className="band part" id="step-request" tabIndex={-1} aria-labelledby="h-request">
        <PartHead n={4} id="h-request" title="What Auto Ontology was asked, and the SQL it wrote" />
        <p className="measure">
          The question went to Auto Ontology with a hint: follow calls backwards, and include callback references. It also named the two columns
          the answer had to contain.
        </p>
        <RequestBlock request={request.request} contract={request.output_contract} />
        <p className="measure sql-intro">
          From that, Auto Ontology’s agent wrote one SQL query. It starts at the resolver, repeatedly looks up who calls the current function,
          accepts callback references as calls, skips test files and keeps each caller’s smallest <Term id="depth">depth</Term>. That summary
          was written for this website; the query below is exactly as recorded.
        </p>
        <SqlPair sql={sql.sql} reference={sql.reference_sql} />
      </section>
      <section className="band part" id="step-answer" tabIndex={-1} aria-labelledby="h-answer">
        <PartHead n={5} id="h-answer" title="The rows that came back" />
        <p className="measure">
          Auto Ontology returned four callers, with <Sym id={SCHEDULER} lower /> at depth 3. These are the recorded rows; switching the graph in
          step 3 does not change them.
        </p>
        <Results tables={answer.result_tables} referenceText={answer.reference_rows} contract={request.output_contract} score={answer.score} />
        <AnswerProse text={answer.answer} />
        <AssessmentBlock assessment={answer.assessment} score={answer.score} finding={answer.review_finding} />
        <p className="small">
          <a href={href({ view: "question", id: w.question_id })} onClick={onLinkClick}>
            Open question {w.question_id}'s complete record
          </a>
        </p>
      </section>
      <OutcomesTeaser />
      <Limits model={model} />
    </>
  );
}

function PartHead({ n, id, title }: { n: number; id: string; title: string }) {
  return (
    <h2 id={id} className="part__title">
      <span className="part__n">Step {n}</span>
      {title}
    </h2>
  );
}

function SourcePart({ source }: { source: SourceStep }) {
  const call = source.spans.find((s) => s.id === `call:${CALLBACK_ID}`);
  return (
    <section className="band part" id="step-source" tabIndex={-1} aria-labelledby="h-source">
      <PartHead n={1} id="h-source" title="The line of Python" />
      <div className="split">
        <div className="measure">
          <p>
            Line {call?.line_start ?? 203} of Auto Ontology’s scheduler does not call <Term id="wrapper">the wrapper</Term>. It passes the
            wrapper to <Term id="to_thread">asyncio.to_thread</Term>, which runs it on another thread. A search for calls of the wrapper would
            miss this line, yet the scheduler depends on the wrapper running.
          </p>
          <p>
            The extractor records the line anyway, as a <Term id="callback">callback reference</Term>. That record says where the wrapper is
            handed over; it does not show that the wrapper ran.
          </p>
          {call ? (
            <p className="actions actions--small">
              <a className="btn-ghost" href={href({ view: "source", span: call.id })} onClick={onLinkClick}>
                Open the scheduler’s file at line {call.line_start}
              </a>
            </p>
          ) : null}
        </div>
        {call ? (
          <Excerpt text={call.excerpt} start={call.excerpt_line_start} mark={[call.line_start]} label={`The scheduler’s file around line ${call.line_start}`} />
        ) : (
          <p className="gate">The source excerpt is not in this publication.</p>
        )}
      </div>
    </section>
  );
}

function firstSentence(text: string): string {
  const m = text.match(/^.*?[.!?](\s|$)/);
  return (m ? m[0] : text).trim();
}

function TablesPart({ records, model }: { records: RecordsStep; model: ModelStep }) {
  const call = records.records.calls.find((c) => c.call_id === CALLBACK_ID);
  const [raw, setRaw] = useState(false);
  const term = (name: string): ModelTerm | undefined => model.terms.find((t) => t.name === name);
  const tables: { key: string; title: string; holds: string; columns: string[]; term?: ModelTerm }[] = [
    {
      key: "calls",
      title: "Calls",
      holds: "One row for each place a function calls or refers to another.",
      columns: ["which function makes the call", "which function it calls", "direct call or callback", "line number"],
      term: term("Call site"),
    },
    {
      key: "symbols",
      title: "Functions and classes",
      holds: "One row for each function, method and class.",
      columns: ["name", "function, method or class", "which file it is in", "first and last line", "first line of its docstring"],
      term: term("Code symbol"),
    },
    {
      key: "files",
      title: "Files",
      holds: "One row for each Python file.",
      columns: ["path", "module name", "whether it is a test file", "its docstring"],
      term: term("Source file"),
    },
  ];
  return (
    <section className="band part" id="step-records" tabIndex={-1} aria-labelledby="h-records">
      <PartHead n={2} id="h-records" title="What the extractor writes" />
      <p className="measure">
        The extractor reads every Python file and fills a <Term id="duckdb">DuckDB</Term> database. Three of its eight tables matter here.
        Beside the database it writes the <Term id="semantic-model">semantic model</Term>, which describes each table in English so that
        Auto Ontology’s agent knows where to look.
      </p>
      <ol className="schema" aria-label="Three tables and how they link">
        {tables.map((t, i) => (
          <li key={t.key} className="schema__item">
            <div className={`schema__card ${t.key === "calls" ? "is-focus" : ""}`}>
              <h3 className="schema__title">{t.title}</h3>
              <p className="schema__holds">{t.holds}</p>
              <p className="schema__label">Each row records</p>
              <ul className="schema__cols">
                {t.columns.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
              {t.term ? (
                <p className="schema__model">
                  <span className="schema__label">The semantic model calls this “{t.term.name}”:</span> {firstSentence(t.term.description)}
                </p>
              ) : null}
            </div>
            {i < tables.length - 1 ? (
              <p className="schema__link">
                <span className="schema__arrow" aria-hidden="true" />
                <span>{i === 0 ? "caller and callee each point to a function" : "each function points to its file"}</span>
              </p>
            ) : null}
          </li>
        ))}
      </ol>
      {call ? (
        <div className="example-row">
          <h3>The row for line {call.line}</h3>
          <div className="table-wrap">
            <table className="rows">
              <caption className="visually-hidden">The Calls row the extractor wrote for line {call.line}</caption>
              <thead>
                <tr>
                  <th scope="col">Caller</th>
                  <th scope="col">Callee</th>
                  <th scope="col">Kind</th>
                  <th scope="col" className="num">Line</th>
                </tr>
              </thead>
              <tbody>
                <tr className="is-focus">
                  <td><Sym id={call.caller_symbol_id} /></td>
                  <td>{call.callee_symbol_id ? <Sym id={call.callee_symbol_id} /> : call.callee_name}</td>
                  <td><Term id="callback">callback</Term></td>
                  <td className="num">{call.line}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="small measure">
            Read as a sentence: at line {call.line}, the scheduler refers to the wrapper by passing it as a callback. The extractor rates the
            match “{call.confidence}” confidence, because passing a function is weaker evidence than calling it.
          </p>
          <p className="record__tools">
            <button type="button" className="btn-quiet" aria-expanded={raw} onClick={() => setRaw(!raw)}>
              {raw ? "Hide" : "Show"} the exact record
            </button>
            <CopyButton text={call.call_id} label="Copy call ID" />
          </p>
          {raw ? <pre className="captured">{JSON.stringify(call, null, 2)}</pre> : null}
        </div>
      ) : null}
    </section>
  );
}

type Preset = "all" | "direct";

function GraphPart({ records }: { records: RecordsStep }) {
  const saved = entryState().view ?? {};
  const [preset, setPreset] = useState<Preset>(saved.preset === "direct" ? "direct" : "all");
  const [selection, setSelection] = useState<Selection>((saved.selection as Selection | undefined) ?? { kind: "edge", id: CALLBACK_ID });
  const all = records.graphs.all_relationships;
  const direct = records.graphs.direct_only;
  const shown = preset === "all" ? all : direct;
  const callers = shown.nodes.filter((n) => n.symbol_id !== shown.root);

  useEffect(() => replaceView({ preset, selection }), [preset, selection]);

  const selectedNode = selection?.kind === "node" ? all.nodes.find((n) => n.symbol_id === selection.id) : undefined;
  const selectedEdge = selection?.kind === "edge" ? all.edges.find((e) => e.call_id === selection.id) : undefined;
  const excluded =
    (selectedNode && !shown.nodes.some((n) => n.symbol_id === selectedNode.symbol_id)) ||
    (selectedEdge && !shown.edges.some((e) => e.call_id === selectedEdge.call_id));
  const depthHere = selectedNode ? shown.nodes.find((n) => n.symbol_id === selectedNode.symbol_id)?.depth : undefined;
  const lower = (id: string | null) => roleOf(id ?? "").toLowerCase();

  return (
    <section className="band part part--graph" id="step-graph" tabIndex={-1} aria-labelledby="h-graph">
      <PartHead n={3} id="h-graph" title="Following calls backwards from the resolver" />
      <p className="measure">
        Each arrow is a row in the Calls table, pointing from caller to callee. To answer the question, the calls are followed backwards from the
        resolver. Switch between the two views to see what the callback row adds.
      </p>
      <div className="preset" role="radiogroup" aria-label="Which calls to follow">
        <button type="button" role="radio" aria-checked={preset === "direct"} className="preset__opt" onClick={() => setPreset("direct")}>
          Direct calls only
        </button>
        <button type="button" role="radio" aria-checked={preset === "all"} className="preset__opt" onClick={() => setPreset("all")}>
          Direct calls and callbacks
        </button>
      </div>
      <p className="graph-sentence" aria-live="polite">
        {preset === "direct"
          ? `Direct calls alone reach ${callers.length} callers. The scheduler is missing, because it never calls the wrapper.`
          : `With callbacks included, ${callers.length} callers are reached. The dashed arrow from the scheduler adds the fourth.`}
      </p>
      <div className="graph-layout">
        <CallerGraph layoutGraph={all} shown={shown} selection={selection} onSelect={setSelection} />
        <div className="graph-below">
          <aside className="inspect" aria-label="Selected item">
            {selectedNode ? (
              <>
                <p className="inspect__kind">{selectedNode.kind === "method" ? "A method" : "A function"}</p>
                <h3 className="inspect__title">{roleOf(selectedNode.symbol_id)}</h3>
                <p>{ROLES[selectedNode.symbol_id]?.what}</p>
                {excluded ? (
                  <p className="notice">
                    Not reached when only direct calls are followed.{" "}
                    <button type="button" className="link-button" onClick={() => setPreset("all")}>
                      Include callbacks
                    </button>
                  </p>
                ) : selectedNode.symbol_id === shown.root ? (
                  <p className="small">The function the question starts from.</p>
                ) : (
                  <p className="small">
                    <Term id="depth">Depth</Term> {depthHere} in this view.
                  </p>
                )}
                <p className="actions actions--small">
                  <a className="btn-ghost" href={href({ view: "source", span: `symbol:${selectedNode.symbol_id}` })} onClick={onLinkClick}>
                    Open its definition
                  </a>
                  <CopyButton text={selectedNode.symbol_id} label="Copy symbol ID" />
                </p>
              </>
            ) : selectedEdge ? (
              <>
                <p className="inspect__kind">{selectedEdge.call_kind === "callback" ? "A callback reference" : "A direct call"}</p>
                <h3 className="inspect__title">
                  {roleOf(selectedEdge.caller_symbol_id)} to {roleOf(selectedEdge.callee_symbol_id ?? "")}
                </h3>
                <p>
                  {selectedEdge.call_kind === "callback"
                    ? `At line ${selectedEdge.line}, the ${lower(selectedEdge.caller_symbol_id)} passes the ${lower(selectedEdge.callee_symbol_id)} to asyncio.to_thread.`
                    : `At line ${selectedEdge.line}, the ${lower(selectedEdge.caller_symbol_id)} calls the ${lower(selectedEdge.callee_symbol_id)}.`}
                </p>
                {excluded ? (
                  <p className="notice">
                    Hidden in this view, which follows direct calls only.{" "}
                    <button type="button" className="link-button" onClick={() => setPreset("all")}>
                      Include callbacks
                    </button>
                  </p>
                ) : null}
                <p className="actions actions--small">
                  <a className="btn-ghost" href={href({ view: "source", span: `call:${selectedEdge.call_id}` })} onClick={onLinkClick}>
                    Open line {selectedEdge.line}
                  </a>
                </p>
              </>
            ) : (
              <p className="small muted">Select a box or an arrow.</p>
            )}
          </aside>
          <div>
            <div className="table-wrap">
              <table className="rows rows--compact">
                <caption>Callers in this view</caption>
                <thead>
                  <tr>
                    <th scope="col">Caller</th>
                    <th scope="col" className="num">Depth</th>
                  </tr>
                </thead>
                <tbody>
                  {[...callers].sort((a, b) => a.depth - b.depth || (a.symbol_id < b.symbol_id ? -1 : 1)).map((n) => (
                    <tr key={n.symbol_id}>
                      <td>
                        <button type="button" className="link-button" onClick={() => setSelection({ kind: "node", id: n.symbol_id })}>
                          {roleOf(n.symbol_id)}
                        </button>
                        <span className="caller-what">{ROLES[n.symbol_id]?.what}</span>
                      </td>
                      <td className="num">{n.depth}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted">Worked out by this website from the saved Calls rows. Auto Ontology’s own answer is in step 5.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function OutcomesTeaser() {
  const outcomes = useRoute<Outcomes>(OUTCOMES);
  return (
    <section className="band band--tint" aria-labelledby="h-outcomes">
      <h2 id="h-outcomes">All 22 recorded questions</h2>
      <Gate loaded={outcomes} what="the outcome list">
        {(o) => {
          const picks = [o.items.find((i) => i.question_id === 2), o.items.find((i) => i.question_id === 14)];
          return (
            <>
              <p className="measure">
                Question 11 is one of {o.population_total}. For {o.population_counts.table_match.pass ?? 0} of them, the rows Auto Ontology
                returned were exactly the expected rows. The author read every written answer and judged{" "}
                {o.population_counts.prose_review.substantive ?? 0} of them adequate. The author wrote the questions while developing the project,
                so this is not an independent benchmark. Two answers fell short in different ways:
              </p>
              <ul className="cases">
                {picks.map((q) =>
                  q ? (
                    <li key={q.question_id}>
                      <a href={href({ view: "question", id: q.question_id })} onClick={onLinkClick} className="cases__link">
                        Question {q.question_id}: {q.question}
                      </a>
                      <span className="cases__status">
                        <TableStatus value={q.assessment.table_match} /> <ProseStatus value={q.assessment.prose_review} />
                      </span>
                      <span className="small">{q.question_id === 2 ? q.review_finding?.reason : q.review_finding?.prose ?? q.review_finding?.reason}</span>
                    </li>
                  ) : null,
                )}
              </ul>
              <p>
                <a className="btn-ghost" href="#/outcomes" onClick={onLinkClick}>
                  See all 22 recorded questions
                </a>
              </p>
            </>
          );
        }}
      </Gate>
    </section>
  );
}

const STAGE_WORDS: Record<string, { name: string; recorded: string }> = {
  compiled_terms: { name: "Auto Ontology’s list of table descriptions after import", recorded: "Recorded, partly: names and descriptions only" },
  submitted_import: { name: "The exact data Auto Ontology received on import", recorded: "" },
  catalog_id_mapping: { name: "How exported names were mapped to Auto Ontology’s internal IDs", recorded: "" },
  compiled_model: { name: "Auto Ontology’s full compiled model", recorded: "" },
  retrieved_context: { name: "Which table descriptions the agent looked up for each question", recorded: "" },
};

function Limits({ model }: { model: ModelStep }) {
  return (
    <section className="band band--plain" id="step-limits" tabIndex={-1} aria-labelledby="h-limits">
      <h2 id="h-limits">What the recording contains</h2>
      <p className="measure">
        The run saved the semantic model the extractor wrote, every question, the SQL and the rows. Some of Auto Ontology’s internal steps were
        not saved, so this website does not show or animate them.
      </p>
      <ul className="stages">
        <li>
          <span>The semantic model the extractor wrote</span>
          <span className="status status--pass">{model.exported_input.status === "recorded" ? "Recorded" : model.exported_input.status}</span>
        </li>
        {Object.entries(model.stages).map(([key, stage]) => {
          const words = STAGE_WORDS[key];
          const recorded = stage.status === "recorded";
          return (
            <li key={key}>
              <span>{words?.name ?? key}</span>
              <span className={`status ${recorded ? "status--partial" : "status--unknown"}`}>{recorded ? words?.recorded || "Recorded" : "Not recorded"}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
