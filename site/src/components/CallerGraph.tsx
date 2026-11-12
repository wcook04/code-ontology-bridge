// The caller graph for the example, drawn from the published graph presets.
// Positions come from the all-relationships preset's depths and never move:
// switching to direct calls only greys out what that preset does not reach,
// so the reader sees which relationship makes the difference.
// Boxes carry the plain role name and the distance only; the exact function name is in the
// accessible label, the inspector and the rows beside the graph.
// Arrows always point from caller to callee. Hover previews; click or Enter selects.

import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Graph } from "../data/types";
import { qualname, roleOf } from "../app/roles";

export type Selection = { kind: "node"; id: string } | { kind: "edge"; id: string } | null;

interface Props {
  layoutGraph: Graph;
  shown: Graph;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  /** Prefix for the arrowhead ids, so two graphs on one page do not share them. */
  idPrefix?: string;
}

interface Box {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

function layout(graph: Graph, vertical: boolean): { boxes: Map<string, Box>; width: number; height: number } {
  const maxDepth = Math.max(...graph.nodes.map((n) => n.depth));
  const columns = new Map<number, string[]>();
  for (const n of [...graph.nodes].sort((a, b) => (a.symbol_id < b.symbol_id ? -1 : 1))) {
    columns.set(n.depth, [...(columns.get(n.depth) ?? []), n.symbol_id]);
  }
  const widest = Math.max(...[...columns.values()].map((c) => c.length));
  const boxes = new Map<string, Box>();
  if (!vertical) {
    const w = 236, h = 64, gapX = 96, gapY = 40;
    const height = widest * h + (widest - 1) * gapY + 24;
    for (const [depth, ids] of columns) {
      const x = 12 + (maxDepth - depth) * (w + gapX);
      const total = ids.length * h + (ids.length - 1) * gapY;
      ids.forEach((id, i) => boxes.set(id, { id, x, y: (height - total) / 2 + i * (h + gapY), w, h }));
    }
    return { boxes, width: 24 + (maxDepth + 1) * w + maxDepth * gapX, height };
  }
  const w = 158, h = 58, gapX = 16, gapY = 48;
  const width = widest * w + (widest - 1) * gapX + 8;
  for (const [depth, ids] of columns) {
    const y = 8 + (maxDepth - depth) * (h + gapY);
    const total = ids.length * w + (ids.length - 1) * gapX;
    ids.forEach((id, i) => boxes.set(id, { id, x: (width - total) / 2 + i * (w + gapX), y, w, h }));
  }
  return { boxes, width, height: 16 + (maxDepth + 1) * h + maxDepth * gapY };
}

function edgePath(from: Box, to: Box, vertical: boolean, shift = 0): { d: string; mid: [number, number] } {
  if (!vertical) {
    const x1 = from.x + from.w, y1 = from.y + from.h / 2, x2 = to.x - 3, y2 = to.y + to.h / 2 + shift;
    const c = (x2 - x1) / 2;
    return { d: `M${x1},${y1} C${x1 + c},${y1} ${x2 - c},${y2} ${x2},${y2}`, mid: [(x1 + x2) / 2, (y1 + y2) / 2] };
  }
  const x1 = from.x + from.w / 2, y1 = from.y + from.h, x2 = to.x + to.w / 2 + shift, y2 = to.y - 3;
  const c = (y2 - y1) / 2;
  return { d: `M${x1},${y1} C${x1},${y1 + c} ${x2},${y2 - c} ${x2},${y2}`, mid: [(x1 + x2) / 2, (y1 + y2) / 2] };
}

function activate(event: KeyboardEvent, run: () => void): void {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    run();
  }
}

export function CallerGraph({ layoutGraph, shown, selection, onSelect, idPrefix = "" }: Props) {
  const frame = useRef<HTMLDivElement>(null);
  const [vertical, setVertical] = useState(false);
  const [preview, setPreview] = useState<Selection>(null);

  useLayoutEffect(() => {
    const el = frame.current;
    if (!el) return;
    const measure = () => setVertical(el.clientWidth < 620);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  useEffect(() => setPreview(null), [shown]);

  const { boxes, width, height } = layout(layoutGraph, vertical);
  const shownNodes = new Set(shown.nodes.map((n) => n.symbol_id));
  const shownEdges = new Set(shown.edges.map((e) => e.call_id));
  const isSelected = (kind: "node" | "edge", id: string) => selection?.kind === kind && selection.id === id;
  const isPreview = (kind: "node" | "edge", id: string) => preview?.kind === kind && preview.id === id;

  return (
    <div className="graph" ref={frame}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        style={{ maxWidth: `${width}px`, aspectRatio: `${width} / ${height}` }}
        role="group"
        aria-label={`Caller graph, ${shown.call_kind === "direct" ? "direct calls only" : "direct calls and callback references"}. Arrows point from caller to callee. A list of the same relationships follows the drawing.`}
      >
        <defs>
          <marker id={`${idPrefix}arrow`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="arrow" />
          </marker>
          <marker id={`${idPrefix}arrow-cb`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="arrow arrow--cb" />
          </marker>
        </defs>
        {layoutGraph.edges.map((edge) => {
          const from = boxes.get(edge.caller_symbol_id);
          const to = edge.callee_symbol_id ? boxes.get(edge.callee_symbol_id) : undefined;
          if (!from || !to) return null;
          // Edges that arrive at one box land side by side, so their arrowheads do not overlap.
          const arriving = layoutGraph.edges.filter((e) => e.callee_symbol_id === edge.callee_symbol_id);
          const place = arriving.findIndex((e) => e.call_id === edge.call_id);
          const shift = (place - (arriving.length - 1) / 2) * (vertical ? 44 : 22);
          const { d } = edgePath(from, to, vertical, shift);
          const callback = edge.call_kind === "callback";
          const present = shownEdges.has(edge.call_id);
          const cls = ["edge", callback ? "edge--cb" : "", present ? "" : "edge--ghost", isSelected("edge", edge.call_id) ? "is-selected" : "", isPreview("edge", edge.call_id) ? "is-preview" : ""].join(" ");
          const label = `${callback ? "Callback reference" : "Direct call"} from ${roleOf(edge.caller_symbol_id)} to ${roleOf(edge.callee_symbol_id ?? "")}, line ${edge.line}${present ? "" : ", not part of this view"}`;
          return (
            <g
              key={edge.call_id}
              className={cls}
              role={present ? "button" : undefined}
              tabIndex={present ? 0 : -1}
              aria-hidden={present ? undefined : true}
              aria-label={present ? label : undefined}
              aria-pressed={present ? isSelected("edge", edge.call_id) : undefined}
              onClick={present ? () => onSelect({ kind: "edge", id: edge.call_id }) : undefined}
              onKeyDown={present ? (e) => activate(e, () => onSelect({ kind: "edge", id: edge.call_id })) : undefined}
              onPointerEnter={present ? () => setPreview({ kind: "edge", id: edge.call_id }) : undefined}
              onPointerLeave={() => setPreview(null)}
            >
              <path d={d} className="edge__hit" />
              <path d={d} className="edge__line" markerEnd={`url(#${idPrefix}${callback ? "arrow-cb" : "arrow"})`} />
              {callback && present ? (
                <text x={vertical ? from.x + 6 : from.x + from.w + 10} y={vertical ? from.y + from.h + 26 : from.y + from.h / 2 - 10} textAnchor="start" className="edge__label">
                  callback
                </text>
              ) : null}
            </g>
          );
        })}
        {layoutGraph.nodes.map((node) => {
          const box = boxes.get(node.symbol_id)!;
          const present = shownNodes.has(node.symbol_id);
          const root = node.symbol_id === layoutGraph.root;
          const shownNode = shown.nodes.find((n) => n.symbol_id === node.symbol_id);
          const cls = ["node", root ? "node--root" : "", present ? "" : "node--ghost", isSelected("node", node.symbol_id) ? "is-selected" : "", isPreview("node", node.symbol_id) ? "is-preview" : ""].join(" ");
          const name = qualname(node.symbol_id);
          return (
            <g
              key={node.symbol_id}
              className={cls}
              role="button"
              tabIndex={0}
              aria-label={`${roleOf(node.symbol_id)}: ${name}${present ? (root ? ", the function the question asks about" : `, depth ${shownNode?.depth}`) : ", not reached in this view"}`}
              aria-pressed={isSelected("node", node.symbol_id)}
              onClick={() => onSelect({ kind: "node", id: node.symbol_id })}
              onKeyDown={(e) => activate(e, () => onSelect({ kind: "node", id: node.symbol_id }))}
              onPointerEnter={() => setPreview({ kind: "node", id: node.symbol_id })}
              onPointerLeave={() => setPreview(null)}
            >
              <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={7} className="node__box" />
              <text x={box.x + 14} y={box.y + box.h / 2 - 3} className="node__role">
                {roleOf(node.symbol_id)}
              </text>
              <text x={box.x + 14} y={box.y + box.h / 2 + 16} className="node__depth">
                {!present ? "not reached" : root ? "the function asked about" : `${shownNode?.depth} ${shownNode?.depth === 1 ? "step" : "steps"} away`}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
