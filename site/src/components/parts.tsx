// Small shared parts: captured text, typed table cells, statuses and load states.
// Every captured string is rendered as React text, never as HTML.

import { useState, type ReactNode } from "react";
import type { Loaded } from "../data/useRoute";
import type { Row } from "../data/types";
import { Term } from "./Term";
import { termForSymbol } from "../app/glossary";
import { roleOf } from "../app/roles";

/** A source excerpt with its real line numbers; `mark` lines are highlighted. */
export function Excerpt({ text, start, mark, label }: { text: string; start: number; mark: number[]; label: string }) {
  const raw = text.replace(/\n$/, "").split("\n");
  // Indentation every non-blank line shares is trimmed for width; the code is otherwise as captured.
  const indent = Math.min(...raw.filter((l) => l.trim()).map((l) => l.match(/^ */)![0].length));
  const lines = raw.map((l) => l.slice(Math.min(indent, l.match(/^ */)![0].length)));
  return (
    <figure className="excerpt" aria-label={label}>
      {indent > 0 ? <figcaption className="visually-hidden">{indent} spaces of shared indentation trimmed.</figcaption> : null}
      <pre tabIndex={0}>
        <code>
          {lines.map((line, i) => {
            const n = start + i;
            const marked = mark.includes(n);
            return (
              <span key={n} className={marked ? "line line--mark" : "line"}>
                <span className="line__n" aria-hidden="true">
                  {n}
                </span>
                <span className="line__t">{line || " "}</span>
                {marked ? <span className="visually-hidden"> (highlighted line {n})</span> : null}
              </span>
            );
          })}
        </code>
      </pre>
    </figure>
  );
}

/** Captured text shown exactly, with wrapping for reading. */
export function Captured({ text, className, label }: { text: string; className?: string; label?: string }) {
  return (
    <pre className={`captured ${className ?? ""}`} tabIndex={0} aria-label={label}>
      {text}
    </pre>
  );
}

/** One value, with its type kept visible: null, empty string, numbers and booleans read differently. */
export function Value({ value }: { value: unknown }) {
  if (value === null) return <span className="v v--null">null</span>;
  if (value === undefined) return <span className="v v--missing">missing</span>;
  if (value === "") return <span className="v v--empty">empty string</span>;
  if (typeof value === "number") return <span className="v v--num">{String(value)}</span>;
  if (typeof value === "boolean") return <span className="v v--bool">{String(value)}</span>;
  if (typeof value === "string") {
    const term = termForSymbol(value);
    if (term) {
      return (
        <span className="v v--sym">
          <Term id={term}>{roleOf(value)}</Term>
          <SymbolId id={value} />
        </span>
      );
    }
    return <span className="v v--str">{/[/:]/.test(value) && !/\s/.test(value) ? <SymbolId id={value} /> : value}</span>;
  }
  return <span className="v v--json">{JSON.stringify(value)}</span>;
}

/** Rows exactly as recorded, in their recorded order and multiplicity. */
export function RowsTable({
  rows,
  columns,
  caption,
  rowNote,
}: {
  rows: Row[];
  columns: string[];
  caption: ReactNode;
  rowNote?: (row: Row, index: number) => ReactNode;
}) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={typeof caption === "string" ? caption : "Result rows"}>
      <table className="rows">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="rows__n">
              Row
            </th>
            {columns.map((c) => (
              <th scope="col" key={c}>
                <code>{c}</code>
              </th>
            ))}
            {rowNote ? <th scope="col">Note</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length + (rowNote ? 2 : 1)} className="rows__empty">
                The recorded result contains no rows.
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i}>
                <td className="rows__n">{i + 1}</td>
                {columns.map((c) => (
                  <td key={c}>
                    <Value value={Object.prototype.hasOwnProperty.call(row, c) ? row[c] : undefined} />
                  </td>
                ))}
                {rowNote ? <td className="rows__note">{rowNote(row, i)}</td> : null}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function TableStatus({ value }: { value: string }) {
  const words: Record<string, string> = { pass: "Rows matched", fail: "Rows did not match", unknown: "Not assessed" };
  return <span className={`status status--${value === "pass" ? "pass" : value === "fail" ? "fail" : "unknown"}`}>{words[value] ?? value}</span>;
}

export function ProseStatus({ value }: { value: string }) {
  const words: Record<string, string> = { substantive: "Substantive", fail: "Prose failed", unknown: "Not classified" };
  return <span className={`status status--${value === "substantive" ? "pass" : value === "fail" ? "fail" : "unknown"}`}>{words[value] ?? value}</span>;
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="btn-quiet"
      onClick={() => {
        navigator.clipboard?.writeText(text).then(
          () => {
            setDone(true);
            window.setTimeout(() => setDone(false), 1600);
          },
          () => undefined,
        );
      }}
    >
      {done ? "Copied" : label}
      <span className="visually-hidden" aria-live="polite">
        {done ? " copied to the clipboard" : ""}
      </span>
    </button>
  );
}

export function Out({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className="out" href={href} target="_blank" rel="noreferrer">
      {children}
      <span aria-hidden="true">&nbsp;↗</span>
      <span className="visually-hidden"> (opens on another site)</span>
    </a>
  );
}

/** Loading and failure, never confused with an empty result. */
export function Gate<T>({ loaded, children, what }: { loaded: Loaded<T>; children: (data: T) => ReactNode; what: string }) {
  if (loaded.state === "loading") {
    return (
      <p className="gate" role="status">
        Loading {what}…
      </p>
    );
  }
  if (loaded.state === "error") {
    return (
      <div className="gate gate--error" role="alert">
        <p>
          <strong>Could not load {what}.</strong> {loaded.error.message}
        </p>
        <p>Nothing has been substituted. Reload to try again.</p>
      </div>
    );
  }
  return <>{children(loaded.data)}</>;
}

/** An identifier that may break only after "/" or "::", never inside a name. */
export function SymbolId({ id }: { id: string }) {
  const parts = id.split(/(?<=\/|::)/);
  return (
    <code className="sym-id">
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          {i < parts.length - 1 ? <wbr /> : null}
        </span>
      ))}
    </code>
  );
}
