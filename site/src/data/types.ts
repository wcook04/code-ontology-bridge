// Shapes of the published API responses this site reads. They mirror
// code_ontology_bridge/inspection/{walkthrough,api}.py and the OpenAPI document
// published beside them; only the fields the site uses are named.

export type Availability = "snapshot" | "recorded" | "computed_locally" | "not_captured" | string;

export interface Entry {
  schema_version: string;
  manifest: string;
  publication_sha256: string;
  bundle_revision: string;
  source_commit: string;
}

export interface Manifest {
  schema_version: string;
  revision: string;
  publication_sha256: string;
  question_count: number;
  api_routes: Record<string, string>;
  delivery: { entry_route: string; outcomes_route: string; kind: string };
}

export interface Envelope<T> {
  schema_version: string;
  revision: string;
  data: T;
}

export interface Span {
  id: string;
  kind: "symbol" | "call";
  record_id: string;
  path: string;
  repository: string;
  commit: string;
  line_start: number;
  line_end: number;
  excerpt: string;
  excerpt_line_start: number;
  excerpt_status: string;
  file_sha256: string;
  source_url: string;
}

export interface SymbolRow {
  symbol_id: string;
  file_id: string;
  name: string;
  qualname: string;
  kind: string;
  line_start: number;
  line_end: number;
  is_public: boolean;
  summary: string;
  summary_source: string;
}

export interface CallRow {
  call_id: string;
  caller_symbol_id: string;
  callee_symbol_id: string | null;
  callee_name: string;
  call_kind: string;
  line: number;
  resolution: string;
  confidence: string;
}

export interface GraphNode extends SymbolRow {
  depth: number;
  source_url: string;
}

export interface GraphEdge extends CallRow {
  source_url: string;
}

export interface Graph {
  availability: Availability;
  call_kind: string;
  counts: { call_occurrences: number; nodes: number; unique_pairs: number };
  depth: number;
  root: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  semantics: string;
  truncated: boolean;
}

export interface Column {
  id: string;
  name: string;
  type: string;
  description: string;
  is_nullable: boolean;
  is_unique: boolean;
}

export interface Table {
  id: string;
  name: string;
  description: string;
  columns: Column[];
  pk: string[];
}

export interface Term {
  id: string;
  name: string;
  description: string;
  represents: string[];
  columns_attributes: { id: string; name: string; column_id: string; description: string }[];
}

export interface Stage {
  status: string;
  artifact?: string;
  note?: string;
  role?: string;
  terms?: { name: string }[];
}

export interface Assessment {
  table_match: "pass" | "fail" | "unknown";
  prose_review: "substantive" | "fail" | "unknown";
  review_method: string;
  review_basis: string;
}

export interface Score {
  agent_rows: number;
  reference_rows: number;
  strict_rows_pass: boolean;
  order_matches: boolean;
  values_match: boolean;
  schema_complete: boolean;
  pass: boolean;
  issues: unknown[];
}

export interface ReviewFinding {
  prose: string;
  reason: string;
  rows: string;
}

export interface Request {
  question: string;
  evidence: string;
  calculation_only: boolean;
}

export interface OutputContract {
  fields: { name: string; type: string }[];
  ordered: boolean;
  guidance: string;
}

export type Row = Record<string, unknown>;

export interface DisplayLink {
  table_index: number;
  row_index: number;
  column: string;
  identity: string;
  source_url: string;
}

export interface QuestionDetail {
  question_id: number;
  question: string;
  answer: string;
  artifact: string;
  sha256: string;
  assessment: Assessment;
  review_finding: ReviewFinding | null;
  score: Score;
  request: Request;
  output_contract: OutputContract;
  sql: string;
  reference_sql: string;
  result_tables: Row[][];
  reference_rows: string;
  display_annotations: { links: DisplayLink[]; note: string };
}

export interface OutcomeItem {
  question_id: number;
  question: string;
  question_route: string;
  assessment: Assessment;
  review_finding: ReviewFinding | null;
  score: Score;
  walkthrough_routes: string[];
}

export interface Outcomes {
  items: OutcomeItem[];
  total: number;
  population_total: number;
  population_counts: {
    table_match: Record<string, number>;
    prose_review: Record<string, number>;
  };
  note: string;
  scope: string;
}

export interface Step<T = any> {
  id: "source" | "records" | "model" | "request" | "sql" | "answer";
  title: string;
  route: string;
  availability: Availability;
  data: T;
}

export interface SourceStep {
  focus_span_ids: string[];
  spans: Span[];
}

export interface RecordsStep {
  note: string;
  graphs: { all_relationships: Graph; direct_only: Graph };
  records: { calls: CallRow[]; symbols: SymbolRow[] };
}

export interface ModelStep {
  column_ids: string[];
  exported_input: { artifact: string; sha256: string; status: string };
  stages: Record<string, Stage>;
  tables: Table[];
  terms: Term[];
}

export interface RequestStep {
  request: Request;
  output_contract: OutputContract;
}

export interface SqlStep {
  sql: string;
  reference_sql: string;
  note: string;
}

export interface AnswerStep {
  answer: string;
  assessment: Assessment;
  score: Score;
  result_tables: Row[][];
  reference_rows: string;
  review_finding: ReviewFinding | null;
  display_annotations: { links: DisplayLink[]; note: string };
}

export interface Walkthrough {
  id: string;
  title: string;
  short_question: string;
  question_id: number;
  question_route: string;
  note: string;
  captions: string[];
  snapshot: { repo_url: string; commit_sha: string; file_count: number };
  steps: Step[];
}
