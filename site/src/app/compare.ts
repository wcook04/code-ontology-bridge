// Compare returned rows with the reference rows the way the scoring contract
// does for an unordered question: as a multiset of value tuples in the output
// contract's field order. Used only to mark rows; the recorded score stays the
// authority and is shown separately.

import type { Row } from "../data/types";

export function parseReference(text: string): unknown[][] | null {
  try {
    const value = JSON.parse(text);
    return Array.isArray(value) && value.every(Array.isArray) ? value : null;
  } catch {
    return null;
  }
}

export function referenceAsRows(reference: unknown[][], fields: string[]): Row[] {
  return reference.map((tuple) => Object.fromEntries(fields.map((f, i) => [f, i < tuple.length ? tuple[i] : undefined])));
}

const key = (values: unknown[]) => JSON.stringify(values);

/** For each returned row: true when an unused equal reference row exists. */
export function matchRows(rows: Row[], reference: unknown[][], fields: string[]): boolean[] {
  const pool = new Map<string, number>();
  for (const tuple of reference) pool.set(key(tuple), (pool.get(key(tuple)) ?? 0) + 1);
  return rows.map((row) => {
    const k = key(fields.map((f) => row[f]));
    const left = pool.get(k) ?? 0;
    if (left > 0) {
      pool.set(k, left - 1);
      return true;
    }
    return false;
  });
}

/** Reference rows that no returned row matched. */
export function missingReference(rows: Row[], reference: unknown[][], fields: string[]): unknown[][] {
  const pool = rows.map((row) => key(fields.map((f) => row[f])));
  return reference.filter((tuple) => {
    const i = pool.indexOf(key(tuple));
    if (i >= 0) {
      pool.splice(i, 1);
      return false;
    }
    return true;
  });
}
