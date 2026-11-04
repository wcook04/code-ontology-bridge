import { describe, expect, it } from "vitest";
import { capturedFrom, readableSql } from "../src/app/sql";
import { matchRows, missingReference, parseReference } from "../src/app/compare";
import { parse, href } from "../src/app/router";

describe("readable SQL", () => {
  const captured =
    "WITH RECURSIVE callers AS (SELECT c.x FROM code.calls AS c WHERE c.name = 'SELECT FROM x' UNION ALL SELECT 1) SELECT w.caller_id FROM callers AS w ORDER BY depth";
  it("only inserts line breaks, outside quoted text", () => {
    const readable = readableSql(captured);
    expect(readable).toContain("\nFROM code.calls");
    expect(readable).toContain("'SELECT FROM x'");
    expect(capturedFrom(readable)).toBe(captured);
  });
  it("leaves multi-line SQL untouched", () => {
    expect(readableSql("SELECT 1\nFROM t")).toBe("SELECT 1\nFROM t");
  });
});

describe("row comparison", () => {
  const fields = ["description", "description_source"];
  const reference = parseReference('[["Semantic layer", "module_docstring"]]')!;
  it("marks returned rows absent from the reference, as a multiset", () => {
    const rows = [
      { description: "Semantic layer", description_source: "module_docstring" },
      { description: "", description_source: "none" },
      { description: "Semantic layer", description_source: "module_docstring" },
    ];
    expect(matchRows(rows, reference, fields)).toEqual([true, false, false]);
  });
  it("keeps null, empty string and numbers distinct", () => {
    const ref = parseReference('[[null, 1]]')!;
    expect(matchRows([{ a: "", b: 1 }], ref, ["a", "b"])).toEqual([false]);
    expect(matchRows([{ a: null, b: "1" }], ref, ["a", "b"])).toEqual([false]);
    expect(matchRows([{ a: null, b: 1 }], ref, ["a", "b"])).toEqual([true]);
  });
  it("reports reference rows nobody returned", () => {
    expect(missingReference([], reference, fields)).toEqual(reference);
  });
  it("rejects reference text that is not a table", () => {
    expect(parseReference("not json")).toBeNull();
    expect(parseReference('{"a": 1}')).toBeNull();
  });
});

describe("addresses", () => {
  it("round-trips every view", () => {
    for (const h of ["#/", "#/walkthrough/graph", "#/outcomes?table=fail", "#/questions/14"]) {
      expect(href(parse(h))).toBe(h);
    }
    const span = "call:auto_ontology/ingestion_service/semantic_scheduler.py:203:24:0";
    expect(parse(href({ view: "source", span }))).toEqual({ view: "source", span });
  });
  it("names an address that matches nothing", () => {
    expect(parse("#/nowhere/at/all").view).toBe("missing");
  });
});

import { findingFor, proseReading } from "../src/app/findings";

describe("editorial summaries", () => {
  it("are shown only for the columns they were written against", () => {
    expect(findingFor(14, ["resolution", "calls", "pct"])).toBeDefined();
    expect(findingFor(14, ["resolution", "calls"])).toBeUndefined();
    expect(findingFor(99, ["x"])).toBeUndefined();
  });
  it("separate a one-word response from an explanation of the query", () => {
    expect(proseReading("thought").tone).toBe("fail");
    expect(proseReading("This query counts the files in the repository.").tone).toBe("ok");
  });
});
