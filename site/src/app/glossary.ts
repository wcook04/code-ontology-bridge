// Glossary cards for the words the page uses in place of long identifiers.
// Symbol entries keep the exact symbol ID the data uses; prose shows the plain name.

export interface GlossaryEntry {
  id: string;
  label: string;
  text: string;
  identifier?: string;
  identifierLabel?: string;
  where?: string;
  span?: string;
  external?: string;
}

const AO = "auto_ontology/";

function symbol(id: string, label: string, text: string, symbolId: string, lines: string): GlossaryEntry {
  return { id, label, text, identifier: symbolId, identifierLabel: "Symbol ID in the database", where: `${symbolId.split("::")[0]}, ${lines}`, span: `symbol:${symbolId}` };
}

const entries: GlossaryEntry[] = [
  symbol("resolver", "The resolver: resolve_semantic_fks", "The function question 11 asks about. It creates links between database columns that refer to each other (foreign keys).", `${AO}semantic/semantic_fk.py::resolve_semantic_fks`, "lines 91–100"),
  symbol("compiler", "The compiler: _run_semantic_compilation", "Runs Auto Ontology’s semantic compilation and calls the resolver directly.", `${AO}semantic/compile.py::_run_semantic_compilation`, "lines 46–127"),
  symbol("wrapper", "The wrapper: run_semantic_compilation", "A public function that calls the compiler. Its docstring reads “Compile semantic taxonomy, embed all nodes into the VDB, then resolve FK edges.”", `${AO}semantic/compile.py::run_semantic_compilation`, "lines 33–43"),
  symbol("scheduler", "The scheduler: SemanticScheduler._run_once", "A method of Auto Ontology’s ingestion scheduler. At line 203 it does not call the wrapper directly; it passes the wrapper to asyncio.to_thread, which runs it on a worker thread. The extractor records that as a callback reference, a different kind of row from a direct call.", `${AO}ingestion_service/semantic_scheduler.py::SemanticScheduler._run_once`, "lines 132–285"),
  symbol("cli", "The command-line entry: main", "The function that runs when semantic compilation is started from the command line. It calls the wrapper directly.", `${AO}semantic/__main__.py::main`, "lines 21–45"),
  {
    id: "to_thread",
    label: "asyncio.to_thread",
    text: "A function in Python’s standard library. You give it another function, and it runs that function on a separate thread.",
    external: "https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread",
  },
  {
    id: "callback",
    label: "Callback reference",
    text: "A place where code passes a function to another call instead of calling it, as in asyncio.to_thread(f). The extractor records these in the Calls table with the kind “callback”, separate from direct calls. asyncio.to_thread is documented to run the function it receives; for other receiving calls the extractor assumes, without proof, that they do. A callback reference shows where a function is handed over, not that it ran.",
  },
  {
    id: "semantic-model",
    label: "Semantic model",
    text: "A YAML file the extractor writes beside the database. In plain English it says what each table and column holds and which columns link tables together. Auto Ontology imports it so its agent knows where to look before writing SQL.",
  },
  {
    id: "auto-ontology",
    label: "NVIDIA Auto Ontology",
    text: "An open-source system from NVIDIA. You connect a database and describe its tables; you can then ask questions in English, and its agent writes and runs SQL to answer them.",
    external: "https://github.com/NVIDIA/auto-ontology",
  },
  {
    id: "duckdb",
    label: "DuckDB",
    text: "A database that is stored in a single file and runs inside the program reading it. Auto Ontology already has a connector for it, so the extractor writes the code tables as a DuckDB file.",
    external: "https://duckdb.org/",
  },
  {
    id: "depth",
    label: "Depth",
    text: "The smallest number of calls between a function and the resolver. The compiler calls the resolver, so it is at depth 1; the wrapper calls the compiler, so it is at depth 2.",
  },
  {
    id: "call-203",
    label: "The callback at line 203",
    text: "The row the extractor wrote for line 203 of the scheduler’s file, where the scheduler passes the wrapper to asyncio.to_thread.",
    identifier: `${AO}ingestion_service/semantic_scheduler.py:203:24:0`,
    identifierLabel: "Call ID in the database",
    span: `call:${AO}ingestion_service/semantic_scheduler.py:203:24:0`,
  },
];

export const GLOSSARY: Record<string, GlossaryEntry> = Object.fromEntries(entries.map((e) => [e.id, e]));

/** The glossary entry for a symbol ID, when it has one. */
export function termForSymbol(symbolId: string): string | undefined {
  return entries.find((e) => e.identifier === symbolId)?.id;
}
