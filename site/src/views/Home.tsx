// The front page: what the project does, drawn, then one recorded question
// followed in five steps from a line of Python to the rows Auto Ontology
// returned. Prose uses plain names; the exact identifiers are in glossary cards.

import { useEffect, useRef, useState } from "react";
import type { AnswerStep, ModelStep, Outcomes, RecordsStep, RequestStep, SourceStep, SqlStep, Term as ModelTerm, Walkthrough } from "../data/types";
import { useRoute } from "../data/useRoute";
import { CallerGraph, type Selection } from "../components/CallerGraph";
import { SystemDiagram } from "../components/SystemDiagram";
import { HeadlineResult } from "../components/HeadlineResult";
import { Term } from "../components/Term";
import { CopyButton, Excerpt, Gate, Out, ProseStatus, RowsTable, TableStatus } from "../components/parts";
import { RunConfig } from "../components/RunConfig";
import { AnswerProse, AssessmentBlock, RequestBlock, Results, SqlPair } from "../components/Evidence";
import { entryState, href, onLinkClick, replaceView } from "../app/router";
import { ROLES, roleOf } from "../app/roles";
import { termForSymbol } from "../app/glossary";
import { CORRECTIONS_URL } from "../app/findings";

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
    <>
      <section className="hero band" aria-labelledby="hero-title">
        <h1 id="hero-title">Make a Python repository queryable by a SQL agent</h1>
        <p className="lede">
          code-ontology-bridge reads a Python repository and writes two files: a database of its files, functions, calls and imports, and a{" "}
          <Term id="semantic-model">semantic model</Term> describing those tables. Both are in formats{" "}
          <Term id="auto-ontology">NVIDIA Auto Ontology</Term> already imports, so its SQL agent can answer questions about the code.
        </p>
        <p className="recorded">
          This website shows one recorded run: Auto Ontology was asked 22 questions about its own source code. Nothing here runs live.
        </p>
        <HeadlineResult />
        <Stages />
        <p className="headline-result">
          In the recorded example, following direct calls finds three of the four functions that reach{" "}
          <Term id="resolver">resolve_semantic_fks</Term>. The fourth, <Term id="scheduler">a scheduler</Term>, does not call the wrapper directly: at line
          203 it passes it to <Term id="to_thread">asyncio.to_thread</Term>. The extractor records that hand-over, and Auto Ontology’s SQL
          found all four.
        </p>
        <div className="actions">
          <a className="btn" href={href({ view: "home", step: "source" })} onClick={(e) => { e.preventDefault(); jump("source"); }}>
            Follow one question from code to answer
          </a>
          <a className="btn-ghost" href="#/outcomes" onClick={onLinkClick}>
            See the 22 recorded questions
          </a>
        </div>
      </section>
      <section className="band" aria-labelledby="split-title">
        <h2 id="split-title">What this project adds, and what NVIDIA supplies</h2>
        <SystemDiagram onOpen={jump} />
        <p className="small muted measure">
          The arrows show how Auto Ontology is built to work. The run saved what went in and what came out: the database, the semantic model,
          each question, the SQL and the rows. It did not save which table descriptions the agent looked up for a question.
        </p>
        <div className="split-cols">
          <div>
            <h3>Built here</h3>
            <ul className="facts">
              <li>An extractor that parses every Python file git tracks in the repository and records files, functions, methods, classes, calls, imports, base classes, docstrings and links between tests and source files, in eight tables.</li>
              <li>Each call is classified: resolved to a function in the repository, or labelled as a built-in, an external library, a dynamic attribute or unresolved. A call the extractor cannot follow keeps no target rather than a guessed one. Linked calls follow plain names only; the published limits list the patterns, such as a local variable shadowing a module-level name, that can still link the wrong definition.</li>
              <li>Functions passed as arguments, as in <Term id="to_thread">asyncio.to_thread</Term>(f), are recorded as <Term id="callback">callback references</Term>, kept apart from direct calls.</li>
              <li>A <Term id="duckdb">DuckDB</Term> export of the tables and a semantic-model export in Auto Ontology’s own YAML format, both stamped with the source commit. The database keeps each file’s SHA-256; the YAML records a fingerprint of all of them.</li>
              <li>The table keys and joins. At this revision Auto Ontology’s DuckDB connector reports no primary or foreign keys (its get_pks and get_fks return empty tables), so the semantic model is where Auto Ontology learns them: it declares a key for each of the 10 tables and 10 joins, such as <code>code.calls.callee_symbol_id</code> → <code>code.symbols.symbol_id</code>.</li>
            </ul>
          </div>
          <div>
            <h3>Supplied by Auto Ontology</h3>
            <ul className="facts">
              <li>Importing the semantic model into its catalog.</li>
              <li>The SQL agent that reads the table descriptions, writes SQL and explains it.</li>
              <li>The DuckDB connector that runs the SQL.</li>
            </ul>
            <h3>What the run needed</h3>
            <p className="small">
              Auto Ontology at commit <code>cdaf61e</code> with a twelve-file patch: it lets the service use public model APIs and exposes its
              existing SQL-only route through the chat API. The extractor and both exports need no patch and no model.{" "}
              <Out href={`${REPO}/blob/main/examples/auto-ontology/live/upstream-fix/README.md`}>Read what the patch changes</Out>
            </p>
          </div>
        </div>
      </section>
    </>
  );
}

const REPO = "https://github.com/wcook04/code-ontology-bridge";

/** The three stages, before any detail. */
function Stages() {
  return (
    <ol className="stages3" aria-label="How a question about code gets answered">
      <li>
        <span className="stages3__name">Python repository</span>
        <span className="stages3__what">Any Python source; here, Auto Ontology’s own 473 files</span>
      </li>
      <li className="is-ours">
        <span className="stages3__owner">This project</span>
        <span className="stages3__name">Code database and semantic model</span>
        <span className="stages3__what">Tables of functions, calls and imports, described in English</span>
      </li>
      <li>
        <span className="stages3__owner">NVIDIA Auto Ontology</span>
        <span className="stages3__name">SQL answers</span>
        <span className="stages3__what">Its agent turns a question into SQL and runs it</span>
      </li>
    </ol>
  );
}

function jump(id: string): void {
  const target = ALIASES[id] ?? id;
  const el = document.getElementById(`step-${target}`);
  replaceView({}, href({ view: "home", step: target }));
  // Before the example has loaded, the address is enough: the example scrolls to it when it appears.
  if (!el) return;
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

  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      const saved = entryState().scrollY;
      if (saved !== undefined) {
        window.scrollTo(0, saved);
        return;
      }
    }
    // Also when a link changes the step while this page is already open (the header's "Caller example").
    if (stepTarget) document.getElementById(`step-${ALIASES[stepTarget] ?? stepTarget}`)?.scrollIntoView({ block: "start" });
  }, [stepTarget]);

  return (
    <>
      <section className="band walk-intro" aria-labelledby="walk-title">
        <h2 id="walk-title">One question, followed from the code to the answer</h2>
        <p className="lede-2">
          Question {w.question_id} asked: if <Term id="resolver">resolve_semantic_fks</Term> changed, which other functions would be
          affected? Auto Ontology returned four. One of them, <Sym id={SCHEDULER} lower />, never calls any of the others directly.
        </p>
        <p className="measure">
          The request told the agent how to search: follow calls backwards, and include callback references. The agent did not have to work out that
          method itself. What made the answer possible is that the extractor had recorded the line where the scheduler hands a function over, as a row
          the agent could query. The five steps below follow that row from the source to the returned rows.
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
          accepts callback references as calls, keeps each caller’s smallest <Term id="depth">depth</Term>, and removes test files from the
          final list. That summary was written for this website; the query below is exactly as recorded.
        </p>
        <SqlPair sql={sql.sql} reference={sql.reference_sql} />
      </section>
      <section className="band part" id="step-answer" tabIndex={-1} aria-labelledby="h-answer">
        <PartHead n={5} id="h-answer" title="The rows that came back" />
        <p className="measure">
          Auto Ontology returned four callers, with <Sym id={SCHEDULER} lower /> at depth 3. These are the recorded rows; switching the graph in
          step 3 does not change them.
        </p>
        <RowsTable rows={answer.result_tables[0] ?? []} columns={request.output_contract.fields.map((f) => f.name)} caption="Rows Auto Ontology returned, in recorded order" />
        <p className="small">
          {answer.score.strict_rows_pass
            ? `These are exactly the ${answer.score.reference_rows} rows of the reference query, in the same order.`
            : "These differ from the reference rows."}
        </p>
        <details className="evidence__fold">
          <summary>Compare with the reference rows</summary>
          <div className="evidence__body">
            <Results tables={answer.result_tables} referenceText={answer.reference_rows} contract={request.output_contract} score={answer.score} />
          </div>
        </details>
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
                returned were exactly the expected rows. Each response pairs those rows with a short explanation of the query, which Auto Ontology’s agent writes before the query
                runs. The author wrote the questions while developing the project, so this is not an independent benchmark. Two responses
                fell short:
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
                      <span className="small">{q.review_finding?.reason}</span>
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
  compiled_terms: { name: "Auto Ontology’s list of table descriptions after import", recorded: "Saved in part: names and descriptions only" },
  submitted_import: { name: "The exact data Auto Ontology received on import", recorded: "" },
  catalog_id_mapping: { name: "How exported names were mapped to Auto Ontology’s internal IDs", recorded: "" },
  compiled_model: { name: "Auto Ontology’s full compiled model", recorded: "" },
  retrieved_context: { name: "Which table descriptions the agent looked up for each question", recorded: "" },
};

function Limits({ model }: { model: ModelStep }) {
  return (
    <section className="band band--plain" id="step-limits" tabIndex={-1} aria-labelledby="h-limits">
      <h2 id="h-limits">What this run shows, and what it does not</h2>
      <div className="split-cols">
        <div>
          <h3>It shows</h3>
          <ul className="facts">
            <li>Auto Ontology can import the extractor’s semantic model and query its database through the existing DuckDB connector.</li>
            <li>For 21 of 22 questions, the SQL its agent wrote returned exactly the rows of a reference query the author wrote.</li>
            <li>A relationship only the extractor records, a function handed to asyncio.to_thread, reached the final answer: direct calls alone find three of the four callers.</li>
            <li>Every request, SQL statement, returned row and written response is recorded and published unchanged.</li>
          </ul>
        </div>
        <div>
          <h3>It does not show</h3>
          <ul className="facts">
            <li>How much the semantic model helps: no agent was given the same database without it.</li>
            <li>Accuracy on new questions: the author wrote all 22 while developing the project, named the columns to return and gave hints for 18.</li>
            <li>Speed in general: in this run a request took a median of 146 seconds, with three running at a time.</li>
            <li>That every recorded link is right. After the run, two extractor defects were found and fixed: an import inside one function could link a call in another function to the wrong definition, and calls inside a nested function were credited to the enclosing function even when it never ran the nested one. Rebuilding Auto Ontology with the fix removes 21 of the 9,442 linked calls and adds 7; the four question 11 callers are unchanged. <a href={CORRECTIONS_URL} target="_blank" rel="noreferrer">Every changed row&nbsp;↗</a></li>
            <li>What happens at run time: the extractor reads source text, so a recorded call is not proof the code runs, and a missing one is not proof it never happens.</li>
          </ul>
        </div>
      </div>
      <RunConfig />
      <h3>Which stages of the run were saved</h3>
      <ul className="stages">
        <li>
          <span>The semantic model the extractor wrote</span>
          <span className="status status--pass">{model.exported_input.status === "recorded" ? "Saved" : model.exported_input.status}</span>
        </li>
        {Object.entries(model.stages).map(([key, stage]) => {
          const words = STAGE_WORDS[key];
          const recorded = stage.status === "recorded";
          return (
            <li key={key}>
              <span>{words?.name ?? key}</span>
              <span className={`status ${recorded ? "status--partial" : "status--unknown"}`}>{recorded ? words?.recorded || "Saved" : "Not saved"}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
