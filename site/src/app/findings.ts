// The website's own reading of each recorded result. Every sentence is computed
// from the rows Auto Ontology returned; none is Auto Ontology's output. Each
// entry chooses how the rows are shown and states any limit a static map of
// source code puts on the result.

import type { Row } from "../data/types";

export type View = "counts" | "distribution" | "ranking" | "list" | "record" | "comparison" | "graph";

export interface Finding {
  /** The question in plain words. */
  title: string;
  /** What kind of question this is, as a short label. */
  kind: string;
  view: View;
  /** For a ranking: the label column and the number column. */
  rank?: { label: string; value: string; unit: string };
  /** The result in one or two sentences, from the rows. */
  says: (rows: Row[]) => string;
  /** What the result does not show. */
  limit?: string;
  /** Something about the recorded SQL a careful reader should know. */
  sqlNote?: string;
}

const n = (v: unknown) => (typeof v === "number" ? v.toLocaleString("en-GB") : String(v));
const name = (id: unknown) => String(id).split("::").pop() ?? String(id);
const file = (id: unknown) => String(id).split("::")[0].split("/").pop() ?? String(id);
const count = (rows: Row[], noun: string, plural = `${noun}s`) => `${rows.length} ${rows.length === 1 ? noun : plural}`;

const STATIC_CALLS =
  "These are calls the extractor found in the source text. Calls made through dynamic attributes or other indirection are not linked, so a function can have callers this list does not show.";

export const FINDINGS: Record<number, Finding> = {
  1: {
    title: "Which functions call upsert_table_term?",
    kind: "Callers",
    view: "list",
    says: (rows) => {
      const tests = rows.filter((r) => String(r.caller_symbol_id).includes("/tests/")).length;
      return `${count(rows, "function")} call upsert_table_term; ${tests} of them are tests.`;
    },
    limit: STATIC_CALLS,
    sqlNote: "The SQL keeps only callers whose kind is “function”, although the shared instructions say caller questions include methods. On this code the rows still matched the reference.",
  },
  2: {
    title: "What does the semantic package do?",
    kind: "Documentation",
    view: "comparison",
    says: (rows) => {
      const doc = rows.find((r) => r.description);
      return `The package’s docstring reads “${doc?.description ?? ""}” Auto Ontology’s query matched every package whose name contains “semantic”, so it also returned a second package, which has no docstring.`;
    },
  },
  3: {
    title: "Which non-test files have no module docstring?",
    kind: "Documentation",
    view: "list",
    says: (rows) => `${count(rows, "non-test file")} have no module docstring, ${rows.filter((r) => String(r.file_id).endsWith("__init__.py")).length} of them package __init__.py files.`,
  },
  4: {
    title: "Where is resolve_semantic_fks defined, and what does its docstring say?",
    kind: "Lookup",
    view: "record",
    says: (rows) => {
      const r = rows[0] ?? {};
      return `It is defined in ${r.file_id}, lines ${r.line_start}–${r.line_end}. Its docstring reads “${r.summary}”`;
    },
  },
  5: {
    title: "How big is the repository?",
    kind: "Counts",
    view: "counts",
    says: (rows) => {
      const r = rows[0] ?? {};
      return `${n(r.files)} Python files, ${n(r.test_files)} of them test files, containing ${n(r.symbols)} functions, methods and classes.`;
    },
  },
  6: {
    title: "Which commit does the code map describe?",
    kind: "Lookup",
    view: "record",
    says: (rows) => `NVIDIA’s auto-ontology repository at commit ${String(rows[0]?.commit_sha ?? "").slice(0, 12)}.`,
  },
  7: {
    title: "Which public functions in auto_ontology/semantic have no test file linked to them?",
    kind: "Test links",
    view: "list",
    says: (rows) => `${count(rows, "public function")} in auto_ontology/semantic are in files that no test file imports or is named after.`,
    limit: "A test link means a test file imports the source file or has a matching name. A function without one may still be exercised by other tests.",
  },
  8: {
    title: "Which ten functions are called from the most places outside the tests?",
    kind: "Ranking",
    view: "ranking",
    rank: { label: "symbol_id", value: "call_sites", unit: "call sites" },
    says: (rows) =>
      rows.length > 1
        ? `${name(rows[0].symbol_id)} in ${file(rows[0].symbol_id)} is called from ${n(rows[0].call_sites)} places; the next, ${name(rows[1].symbol_id)}, from ${n(rows[1].call_sites)}.`
        : "",
    limit: STATIC_CALLS,
  },
  9: {
    title: "Which files import auto_ontology/dal/terms.py?",
    kind: "Imports",
    view: "list",
    says: (rows) => `${count(rows, "file")} import it, ${rows.filter((r) => String(r.file_id).includes("/tests/")).length} of them tests.`,
    limit: "Only import statements that resolve to a file in the repository are recorded; imports built at run time are not.",
  },
  10: {
    title: "Which test files are linked to semantic_fk.py, and why?",
    kind: "Test links",
    view: "list",
    says: (rows) => {
      const files = new Set(rows.map((r) => r.test_file_id));
      return `${files.size === 1 ? `One test file, ${file([...files][0])},` : `${files.size} test files`} ${files.size === 1 ? "is" : "are"} linked to it, for ${rows.length} reasons: ${rows.map((r) => (r.reason === "imports_target" ? "it imports the file" : r.reason === "name_match" ? "its name matches" : String(r.reason))).join(" and ")}.`;
    },
    limit: "The two rows are two reasons for one link, not two test files. A link is an association found in the source, not a record of which code the test runs.",
  },
  11: {
    title: "Which functions would be affected if resolve_semantic_fks changed?",
    kind: "Callers, recursively",
    view: "graph",
    says: (rows) => `${count(rows, "function")} reach it through calls. One, the scheduler, reaches it only because the extractor recorded a function passed to asyncio.to_thread.`,
    limit: STATIC_CALLS,
    sqlNote: "The SQL removes test files from the final list; it can still pass through a test function while searching. The graph on the front page leaves test functions out of the search itself. Both give the same four callers here.",
  },
  12: {
    title: "Which five packages have the most lines in non-test files?",
    kind: "Ranking",
    view: "ranking",
    rank: { label: "package", value: "lines", unit: "lines" },
    says: (rows) => (rows[0] ? `${rows[0].package} has the most, ${n(rows[0].lines)} lines.` : ""),
    limit: "Lines are counted per file and include blank lines and comments.",
  },
  13: {
    title: "Which five classes define the most methods?",
    kind: "Ranking",
    view: "ranking",
    rank: { label: "symbol_id", value: "methods", unit: "methods" },
    says: (rows) => (rows.length > 1 ? `${name(rows[0].symbol_id)} defines ${n(rows[0].methods)} methods; ${name(rows[1].symbol_id)} follows with ${n(rows[1].methods)}.` : ""),
  },
  14: {
    title: "How many call sites could the extractor link to a function?",
    kind: "Static analysis coverage",
    view: "distribution",
    says: (rows) => {
      const total = rows.reduce((s, r) => s + Number(r.calls), 0);
      const linked = rows.filter((r) => LINKED.has(String(r.resolution))).reduce((s, r) => s + Number(r.calls), 0);
      return `Of ${n(total)} direct calls, ${n(linked)} (${((linked / total) * 100).toFixed(1)}%) were linked to a function or method defined in the repository. The rest were classified without a link: calls through a dynamic attribute, to external libraries or to Python built-ins, and a small remainder marked unresolved.`;
    },
    limit: "“Unresolved” is only the calls the extractor could not classify at all. It is not every call without a link.",
  },
  15: {
    title: "Which connector modules does auto_ontology/connectors/__init__.py import?",
    kind: "Imports",
    view: "list",
    says: (rows) => `It imports ${count(rows, "module")} from its own directory.`,
  },
  16: {
    title: "Which non-test modules have no recorded import from another file?",
    kind: "Imports",
    view: "list",
    says: (rows) => `${count(rows, "module")}, ${rows.filter((r) => String(r.file_id).startsWith("dev_tools/")).length} of them scripts under dev_tools.`,
    limit: "No recorded import is not the same as never imported: modules loaded by name at run time, or started as scripts, do not appear as imports.",
  },
  17: {
    title: "Which functions does _run_semantic_compilation call?",
    kind: "Callees",
    view: "list",
    says: (rows) => `${count(rows, "function")} defined in the repository, the resolver among them.`,
    limit: STATIC_CALLS,
  },
  18: {
    title: "Which packages have the largest share of public symbols without a docstring?",
    kind: "Ranking",
    view: "ranking",
    rank: { label: "package", value: "pct_undocumented", unit: "% undocumented" },
    says: (rows) => (rows[0] ? `In ${rows[0].package}, ${n(rows[0].undocumented)} of ${n(rows[0].public_symbols)} public symbols (${rows[0].pct_undocumented}%) have no docstring, the highest share among packages with at least 20.` : ""),
  },
  19: {
    title: "Which pairs of packages call into each other in both directions?",
    kind: "Package dependencies",
    view: "list",
    says: (rows) => `${count(rows, "pair")} of packages have recorded calls going both ways.`,
    limit: STATIC_CALLS,
  },
  20: {
    title: "Which files depend on auto_ontology/semantic/constants.py through imports?",
    kind: "Imports, recursively",
    view: "ranking",
    rank: { label: "area", value: "files", unit: "files" },
    says: (rows) => {
      const total = rows.reduce((s, r) => s + Number(r.files), 0);
      return rows[0] ? `${n(total)} non-test files import it directly or through other files; ${rows[0].area} has the most, ${n(rows[0].files)}.` : "";
    },
  },
  21: {
    title: "Which test file is linked to the most source files?",
    kind: "Test links",
    view: "record",
    says: (rows) => (rows[0] ? `${file(rows[0].test_file_id)}, in ${String(rows[0].test_file_id).split("/").slice(0, -1).join("/")}, is linked to ${n(rows[0].targets)} source files.` : ""),
    limit: "Links come from imports and matching names, not from running the tests.",
  },
  22: {
    title: "Which connector classes are only ever subclassed, never constructed?",
    kind: "Class hierarchy",
    view: "record",
    says: (rows) => (rows[0] ? `${name(rows[0].symbol_id)} in ${file(rows[0].symbol_id)} has ${n(rows[0].subclasses)} non-test subclasses and no recorded call that constructs it.` : ""),
    limit: "Only constructor calls the extractor could resolve are counted; a class created through a factory or by name at run time would not appear.",
  },
};

/** Resolution kinds that carry a callee in the repository (SPEC.md, code.calls). */
export const LINKED = new Set(["same_file", "imported", "method_on_self"]);

export const RESOLUTION_WORDS: Record<string, string> = {
  imported: "Imported function",
  same_file: "Function in the same file",
  method_on_self: "Method on self",
  dynamic_attribute: "Dynamic attribute, e.g. obj.method()",
  external: "External library",
  builtin: "Python built-in",
  unresolved: "Unresolved",
};

export const COLUMN_WORDS: Record<string, string> = {
  files: "Python files",
  test_files: "test files",
  symbols: "functions, methods and classes",
  repo_url: "Repository",
  commit_sha: "Commit",
  source_fingerprint: "Fingerprint of the analysed files",
  file_id: "File",
  symbol_id: "Symbol",
  line_start: "First line",
  line_end: "Last line",
  summary: "Docstring",
  test_file_id: "Test file",
  targets: "Linked source files",
  subclasses: "Non-test subclasses",
};

/** How the written answer relates to the result, read by this website. */
export function proseReading(answer: string): { label: string; tone: "fail" | "partial" } {
  if (answer.trim().split(/\s+/).length < 3) return { label: "No explanation: the whole answer is one word", tone: "fail" };
  return { label: "Explains the query, but does not state the result", tone: "partial" };
}
