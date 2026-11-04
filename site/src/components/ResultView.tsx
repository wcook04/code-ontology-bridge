// One recorded result, drawn the way its kind of question needs: figures for
// counts, bars for rankings and shares, a readable list for sets of names, a
// record card for one row, and returned-against-expected for a mismatch.
// Values come straight from the recorded rows; only their layout differs.

import type { OutputContract, Row } from "../data/types";
import { COLUMN_WORDS, LINKED, RESOLUTION_WORDS, type Finding } from "../app/findings";
import { matchRows, parseReference, referenceAsRows } from "../app/compare";
import { href, onLinkClick } from "../app/router";
import { SymbolId } from "./parts";

const fmt = (v: unknown) => (typeof v === "number" ? v.toLocaleString("en-GB") : v === null ? "null" : v === "" ? "(empty)" : String(v));

/** A symbol ID or a path, shown as its name with its file underneath. */
function Ident({ value, href: url }: { value: unknown; href?: string }) {
  const s = String(value);
  if (url) {
    return (
      <a className="ident-link" href={url} target="_blank" rel="noreferrer" title="Open this definition at the pinned commit">
        <Ident value={value} />
        <span className="visually-hidden"> (opens the source on GitHub)</span>
      </a>
    );
  }
  if (s.includes("::")) {
    const [path, qual] = s.split("::");
    return (
      <span className="ident">
        <span className="ident__name">{qual}</span>
        <span className="ident__where"><SymbolId id={path} /></span>
      </span>
    );
  }
  if (s.includes("/")) {
    const parts = s.split("/");
    return (
      <span className="ident">
        <span className="ident__name">{parts.pop()}</span>
        <span className="ident__where"><SymbolId id={parts.join("/") + "/"} /></span>
      </span>
    );
  }
  if (/^[\w.]+$/.test(s) && s.includes(".")) {
    const parts = s.split(".");
    return (
      <span className="ident__name">
        {parts.map((p, i) => (
          <span key={i}>
            {i ? "." : ""}
            {i ? <wbr /> : null}
            {p}
          </span>
        ))}
      </span>
    );
  }
  return <span className="ident__name">{s}</span>;
}

export function ResultView({ finding, rows, contract, referenceText, links = {} }: { finding: Finding; rows: Row[]; contract: OutputContract; referenceText: string; links?: Record<string, string> }) {
  const fields = contract.fields.map((f) => f.name);
  const at = (i: number, c: string) => links[`${i}:${c}`];
  switch (finding.view) {
    case "counts":
      return (
        <dl className="figures">
          {fields.map((f) => (
            <div key={f}>
              <dd>{fmt(rows[0]?.[f])}</dd>
              <dt>{COLUMN_WORDS[f] ?? f}</dt>
            </div>
          ))}
        </dl>
      );
    case "distribution":
      return <Distribution rows={rows} />;
    case "ranking": {
      const r = finding.rank!;
      const max = Math.max(...rows.map((row) => Number(row[r.value]) || 0));
      return (
        <ol className="bars">
          {rows.map((row, i) => (
            <li key={i} className="bars__row">
              <span className="bars__label"><Ident value={row[r.label]} href={at(i, r.label)} /></span>
              <span className="bars__track" aria-hidden="true">
                <span className="bars__fill" style={{ width: `${(Number(row[r.value]) / max) * 100}%` }} />
              </span>
              <span className="bars__value">
                {fmt(row[r.value])} <span className="muted">{r.unit}</span>
              </span>
            </li>
          ))}
        </ol>
      );
    }
    case "record":
      return (
        <dl className="record-card">
          {fields.map((f) => (
            <div key={f}>
              <dt>{COLUMN_WORDS[f] ?? f}</dt>
              <dd>{f.endsWith("_id") ? <Ident value={rows[0]?.[f]} href={at(0, f)} /> : fmt(rows[0]?.[f])}</dd>
            </div>
          ))}
        </dl>
      );
    case "comparison": {
      const reference = parseReference(referenceText) ?? [];
      const matched = matchRows(rows, reference, fields);
      return (
        <div className="compare">
          <div>
            <p className="compare__head">Auto Ontology returned {rows.length} rows</p>
            <ul className="compare__list">
              {rows.map((row, i) => (
                <li key={i} className={matched[i] ? "" : "is-extra"}>
                  <span>{fields.map((f) => fmt(row[f])).join(", ")}</span>
                  <span className="compare__tag">{matched[i] ? "expected" : "not expected"}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="compare__head">The reference has {reference.length}</p>
            <ul className="compare__list">
              {referenceAsRows(reference, fields).map((row, i) => (
                <li key={i}>
                  <span>{fields.map((f) => fmt(row[f])).join(", ")}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      );
    }
    case "graph":
      return (
        <div>
          <ol className="plain-list">
            {rows.map((row, i) => (
              <li key={i}>
                <Ident value={row.symbol_id} href={at(i, "symbol_id")} /> <span className="muted small">depth {fmt(row.depth)}</span>
              </li>
            ))}
          </ol>
          <p>
            <a className="btn-ghost" href={href({ view: "home", step: "graph" })} onClick={onLinkClick}>
              See these callers as a graph
            </a>
          </p>
        </div>
      );
    case "list":
    default: {
      const cols = fields;
      return (
        <ol className={`plain-list ${rows.length > 12 ? "plain-list--cols" : ""}`}>
          {rows.map((row, i) => (
            <li key={i}>
              {cols.map((c, j) => (
                <span key={c} className={j ? "plain-list__extra" : undefined}>
                  {c.endsWith("_id") || c.startsWith("package") ? <Ident value={row[c]} href={at(i, c)} /> : <span className="muted small">{c === "reason" ? String(row[c]).replace("_", " ") : fmt(row[c])}</span>}
                </span>
              ))}
            </li>
          ))}
        </ol>
      );
    }
  }
}

function Distribution({ rows }: { rows: Row[] }) {
  const total = rows.reduce((s, r) => s + Number(r.calls), 0);
  const groups = [
    { key: "linked", title: "Linked to a function in the repository", rows: rows.filter((r) => LINKED.has(String(r.resolution))) },
    { key: "classified", title: "Classified, with no function to link to", rows: rows.filter((r) => !LINKED.has(String(r.resolution)) && r.resolution !== "unresolved") },
    { key: "unresolved", title: "Not classified", rows: rows.filter((r) => r.resolution === "unresolved") },
  ];
  return (
    <div className="dist">
      <div className="dist__stack" aria-hidden="true">
        {groups.map((g) => {
          const sum = g.rows.reduce((s, r) => s + Number(r.calls), 0);
          return <span key={g.key} className={`dist__seg dist__seg--${g.key}`} style={{ width: `${(sum / total) * 100}%` }} />;
        })}
      </div>
      <p className="dist__axis">Each bar is drawn on the same scale: its full width would be 100% of all direct calls.</p>
      {groups.map((g) => {
        const sum = g.rows.reduce((s, r) => s + Number(r.calls), 0);
        return (
          <section key={g.key} className={`dist__group dist__group--${g.key}`}>
            <h3 className="dist__title">
              <span className={`dist__key dist__seg--${g.key}`} aria-hidden="true" />
              {g.title}
              <span className="dist__sum">
                {sum.toLocaleString("en-GB")} calls, {((sum / total) * 100).toFixed(1)}%
              </span>
            </h3>
            <ul className="bars bars--tight">
              {g.rows.map((r) => (
                <li key={String(r.resolution)} className="bars__row">
                  <span className="bars__label">
                    {RESOLUTION_WORDS[String(r.resolution)] ?? String(r.resolution)} <code className="muted small">{String(r.resolution)}</code>
                  </span>
                  <span className="bars__track" aria-hidden="true">
                    <span className={`bars__fill dist__seg--${g.key}`} style={{ width: `${Number(r.pct)}%` }} />
                  </span>
                  <span className="bars__value">
                    {Number(r.calls).toLocaleString("en-GB")} <span className="muted">({Number(r.pct).toFixed(1)}%)</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
