// Who does what, drawn. Adapted from the repository’s architecture figure
// (docs/figures/architecture.png, whose required relationships are listed in
// docs/figures/README.md): Python source enters the extractor, which writes a
// database and a semantic model; Auto Ontology imports the model into its
// catalog, its SQL agent writes SQL from a question, and its existing DuckDB
// connector runs that SQL on the database. Ownership is shown by an enclosure
// as well as by colour. Each box opens the step of the example that shows the
// recorded material for it.

import { useLayoutEffect, useRef, useState } from "react";

type Id = "repo" | "extractor" | "database" | "model" | "catalog" | "question" | "agent" | "connector" | "answer";
interface Node {
  id: Id;
  title: string;
  sub: string;
  ours?: boolean;
  person?: boolean;
  step: string;
  open: string;
}

const NODES: Record<Id, Node> = {
  repo: { id: "repo", title: "Python repository", sub: "473 files of Auto Ontology", step: "source", open: "the line of source used in the example", person: true },
  extractor: { id: "extractor", title: "Extractor", sub: "reads every .py file", ours: true, step: "source", open: "the line of source the extractor read" },
  database: { id: "database", title: "Database", sub: "files, functions, calls", ours: true, step: "records", open: "a row the extractor wrote" },
  model: { id: "model", title: "Semantic model", sub: "what each table means", ours: true, step: "model", open: "the model’s description of a table" },
  catalog: { id: "catalog", title: "Semantic catalog", sub: "imports the model", step: "limits", open: "what was recorded about the catalog" },
  question: { id: "question", title: "A question", sub: "“what calls this function?”", person: true, step: "request", open: "the question as submitted" },
  agent: { id: "agent", title: "SQL agent", sub: "writes SQL", step: "sql", open: "the SQL the agent wrote" },
  connector: { id: "connector", title: "DuckDB connector", sub: "runs the SQL", step: "answer", open: "the rows the SQL returned" },
  answer: { id: "answer", title: "Rows and answer", sub: "returned to you", person: true, step: "answer", open: "the recorded rows and written answer" },
};

type Box = { x: number; y: number; w: number; h: number };
interface Layout {
  width: number;
  height: number;
  ours: Box;
  theirs: Box;
  oursLabel: [number, number];
  theirsLabel: [number, number];
  boxes: Record<Id, Box>;
  edges: { from: Id; to: Id; d: string; label?: string; at?: [number, number]; ours?: boolean; both?: boolean }[];
}

const W = 150, H = 64;

const WIDE: Layout = (() => {
  const b: Record<Id, Box> = {
    repo: { x: 16, y: 176, w: 136, h: H },
    extractor: { x: 196, y: 176, w: 124, h: H },
    database: { x: 364, y: 96, w: W, h: H },
    model: { x: 364, y: 262, w: W, h: H },
    connector: { x: 598, y: 96, w: W, h: H },
    catalog: { x: 598, y: 262, w: W, h: H },
    agent: { x: 820, y: 176, w: 132, h: H },
    question: { x: 820, y: 8, w: 132, h: 52 },
    answer: { x: 990, y: 176, w: 124, h: H },
  };
  const right = (n: Box) => [n.x + n.w, n.y + n.h / 2];
  const left = (n: Box) => [n.x, n.y + n.h / 2];
  const curve = (a: number[], c: number[]) => {
    const m = (c[0] - a[0]) / 2;
    return `M${a[0]},${a[1]} C${a[0] + m},${a[1]} ${c[0] - m},${c[1]} ${c[0] - 4},${c[1]}`;
  };
  return {
    width: 1128,
    height: 346,
    ours: { x: 180, y: 66, w: 352, h: 276 },
    theirs: { x: 574, y: 66, w: 400, h: 276 },
    oursLabel: [192, 86],
    theirsLabel: [586, 86],
    boxes: b,
    edges: [
      { from: "repo", to: "extractor", d: curve(right(b.repo), left(b.extractor)) },
      { from: "extractor", to: "database", d: curve(right(b.extractor), left(b.database)), ours: true },
      { from: "extractor", to: "model", d: curve(right(b.extractor), left(b.model)), ours: true },
      { from: "database", to: "connector", d: curve(right(b.database), left(b.connector)), label: "queried by", at: [556, 118] },
      { from: "model", to: "catalog", d: curve(right(b.model), left(b.catalog)), label: "imported into", at: [556, 284] },
      { from: "catalog", to: "agent", d: curve(right(b.catalog), [b.agent.x, b.agent.y + 46]), label: "table meanings", at: [778, 262] },
      { from: "question", to: "agent", d: `M${b.question.x + 66},${b.question.y + b.question.h} L${b.agent.x + 66},${b.agent.y - 4}` },
      { from: "agent", to: "connector", d: `M${b.agent.x - 4},${b.agent.y + 18} C${b.agent.x - 36},${b.agent.y + 18} ${b.connector.x + b.connector.w + 36},${b.connector.y + 32} ${b.connector.x + b.connector.w + 4},${b.connector.y + 32}`, label: "SQL out, rows back", at: [770, 172], both: true },
      { from: "agent", to: "answer", d: curve(right(b.agent), left(b.answer)) },
    ],
  };
})();

const TALL: Layout = (() => {
  const w = 156, h = 60;
  const b: Record<Id, Box> = {
    repo: { x: 102, y: 12, w, h },
    extractor: { x: 102, y: 124, w, h },
    database: { x: 14, y: 228, w, h },
    model: { x: 190, y: 228, w, h },
    connector: { x: 14, y: 376, w, h },
    catalog: { x: 190, y: 376, w, h },
    agent: { x: 102, y: 494, w, h },
    question: { x: 14, y: 610, w, h },
    answer: { x: 190, y: 610, w, h },
  };
  const down = (a: Box, c: Box, ax = 0.5, cx = 0.5) => {
    const p = [a.x + a.w * ax, a.y + a.h], q = [c.x + c.w * cx, c.y - 4];
    const m = (q[1] - p[1]) / 2;
    return `M${p[0]},${p[1]} C${p[0]},${p[1] + m} ${q[0]},${q[1] - m} ${q[0]},${q[1]}`;
  };
  return {
    width: 360,
    height: 684,
    ours: { x: 4, y: 94, w: 352, h: 206 },
    theirs: { x: 4, y: 330, w: 352, h: 236 },
    oursLabel: [14, 114],
    theirsLabel: [14, 350],
    boxes: b,
    edges: [
      { from: "repo", to: "extractor", d: down(b.repo, b.extractor) },
      { from: "extractor", to: "database", d: down(b.extractor, b.database, 0.25, 0.5), ours: true },
      { from: "extractor", to: "model", d: down(b.extractor, b.model, 0.75, 0.5), ours: true },
      { from: "database", to: "connector", d: down(b.database, b.connector) },
      { from: "model", to: "catalog", d: down(b.model, b.catalog) },
      { from: "catalog", to: "agent", d: down(b.catalog, b.agent, 0.5, 0.75) },
      { from: "agent", to: "connector", d: `M${b.agent.x + 30},${b.agent.y - 4} C${b.agent.x + 30},${b.agent.y - 28} ${b.connector.x + 80},${b.connector.y + h + 26} ${b.connector.x + 80},${b.connector.y + h + 4}`, label: "SQL out, rows back", at: [180, 470], both: true },
      { from: "question", to: "agent", d: `M${b.question.x + w / 2},${b.question.y - 4} C${b.question.x + w / 2},${b.question.y - 30} ${b.agent.x + 30},${b.agent.y + h + 26} ${b.agent.x + 30},${b.agent.y + h + 4}` },
      { from: "agent", to: "answer", d: down(b.agent, b.answer, 0.75, 0.5) },
    ],
  };
})();

export function SystemDiagram({ onOpen }: { onOpen: (step: string) => void }) {
  const frame = useRef<HTMLDivElement>(null);
  const [tall, setTall] = useState(false);
  const [hover, setHover] = useState<Id | null>(null);
  useLayoutEffect(() => {
    const el = frame.current;
    if (!el) return;
    const measure = () => setTall(el.clientWidth < 760);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const L = tall ? TALL : WIDE;
  const lit = (id: Id) => hover === id || (hover !== null && L.edges.some((e) => (e.from === hover && e.to === id) || (e.to === hover && e.from === id)));

  return (
    <figure className="system" ref={frame}>
      <svg viewBox={`0 0 ${L.width} ${L.height}`} width="100%" style={{ maxWidth: `${L.width}px` }} role="group" aria-labelledby="system-caption">
        <defs>
          <marker id="sys-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="sys-arrowhead" />
          </marker>
        </defs>
        <rect x={L.ours.x} y={L.ours.y} width={L.ours.w} height={L.ours.h} rx={12} className="sys-region sys-region--ours" />
        <text x={L.oursLabel[0]} y={L.oursLabel[1]} className="sys-region__label sys-region__label--ours">
          This project
        </text>
        <rect x={L.theirs.x} y={L.theirs.y} width={L.theirs.w} height={L.theirs.h} rx={12} className="sys-region sys-region--theirs" />
        <text x={L.theirsLabel[0]} y={L.theirsLabel[1]} className="sys-region__label">
          NVIDIA Auto Ontology
        </text>
        {L.edges.map((e) => (
          <g key={`${e.from}-${e.to}`} className={`sys-edge ${hover && (e.from === hover || e.to === hover) ? "is-lit" : ""} ${e.ours ? "sys-edge--ours" : ""}`} aria-hidden="true">
            <path d={e.d} markerEnd="url(#sys-arrow)" markerStart={e.both ? "url(#sys-arrow)" : undefined} />
            {e.label && e.at ? (
              <text x={e.at[0]} y={e.at[1]} textAnchor="middle" className="sys-edge__label">
                {e.label}
              </text>
            ) : null}
          </g>
        ))}
        {(Object.keys(NODES) as Id[]).map((id) => {
          const n = NODES[id];
          const b = L.boxes[id];
          return (
            <a
              key={id}
              href={`#/walkthrough/${n.step}`}
              className={`sys-node ${n.ours ? "sys-node--ours" : ""} ${n.person ? "sys-node--outside" : ""} ${lit(id) ? "is-lit" : ""}`}
              aria-label={`${n.title}, ${n.sub}${n.ours ? ", built in this project" : n.person ? "" : ", part of NVIDIA Auto Ontology"}. Open ${n.open}.`}
              onClick={(ev) => {
                ev.preventDefault();
                onOpen(n.step);
              }}
              onPointerEnter={() => setHover(id)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(id)}
              onBlur={() => setHover(null)}
            >
              <rect x={b.x} y={b.y} width={b.w} height={b.h} rx={8} className="sys-node__box" />
              <text x={b.x + b.w / 2} y={b.y + b.h / 2 - 3} textAnchor="middle" className="sys-node__title">
                {n.title}
              </text>
              <text x={b.x + b.w / 2} y={b.y + b.h / 2 + 16} textAnchor="middle" className="sys-node__sub">
                {n.sub}
              </text>
            </a>
          );
        })}
      </svg>
      <figcaption id="system-caption" className="system__caption">
        <span className="key key--ours" aria-hidden="true" /> Built in this project: the extractor, and the code database and table descriptions it
        writes. <span className="key key--theirs" aria-hidden="true" /> NVIDIA Auto Ontology, used through the import and DuckDB connector it
        already has. Select any box to see the recorded material for it.
      </figcaption>
    </figure>
  );
}
