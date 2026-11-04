// A reading layout for captured SQL. It only inserts line breaks before
// top-level clause keywords outside quoted text, so removing the inserted
// breaks gives back the captured statement exactly (tests/sql.test.ts).

const CLAUSES = [
  "WITH RECURSIVE",
  "UNION ALL",
  "SELECT",
  "FROM",
  "INNER JOIN",
  "LEFT JOIN",
  "JOIN",
  "WHERE",
  "GROUP BY",
  "ORDER BY",
  "HAVING",
  "LIMIT",
];

export const BREAK = "\n";

/** Captured SQL with a line break inserted before each clause keyword (single-line statements only). */
export function readableSql(sql: string): string {
  if (sql.includes("\n")) return sql;
  let out = "";
  let quote: string | null = null;
  for (let i = 0; i < sql.length; i++) {
    const ch = sql[i];
    if (quote) {
      out += ch;
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === "'" || ch === '"') {
      quote = ch;
      out += ch;
      continue;
    }
    if (i > 0 && sql[i - 1] === " ") {
      const rest = sql.slice(i);
      const hit = CLAUSES.find((k) => rest.startsWith(k) && !/[A-Za-z0-9_]/.test(rest.charAt(k.length)));
      if (hit) {
        out = out.slice(0, -1) + BREAK;
      }
    }
    out += ch;
  }
  return out;
}

/** Inverse of readableSql for a single-line capture: put the replaced spaces back. */
export function capturedFrom(readable: string): string {
  return readable.split(BREAK).join(" ");
}
