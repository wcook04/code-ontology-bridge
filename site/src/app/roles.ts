// Short role names for the five symbols in the caller example. They are
// editorial display labels, matching the README’s diagram, and are always
// shown beside the exact symbol ID; the site selects and links by the ID.

export const ROLES: Record<string, { role: string; what: string }> = {
  "auto_ontology/semantic/semantic_fk.py::resolve_semantic_fks": {
    role: "Resolver",
    what: "The function the question asks about. It creates semantic foreign-key links.",
  },
  "auto_ontology/semantic/compile.py::_run_semantic_compilation": {
    role: "Compiler",
    what: "Runs semantic compilation and calls the resolver directly.",
  },
  "auto_ontology/semantic/compile.py::run_semantic_compilation": {
    role: "Wrapper",
    what: "A public wrapper that calls the compiler.",
  },
  "auto_ontology/ingestion_service/semantic_scheduler.py::SemanticScheduler._run_once": {
    role: "Scheduler",
    what: "A scheduler method that hands the wrapper to asyncio.to_thread instead of calling it.",
  },
  "auto_ontology/semantic/__main__.py::main": {
    role: "CLI entry",
    what: "The command-line entry point, which calls the wrapper directly.",
  },
};

export function roleOf(symbolId: string): string {
  return ROLES[symbolId]?.role ?? symbolId.split("::").pop() ?? symbolId;
}

/** The part of a symbol ID after the file path. */
export function qualname(symbolId: string): string {
  return symbolId.split("::").pop() ?? symbolId;
}

export function filePart(symbolId: string): string {
  return symbolId.split("::")[0];
}
