// Glossary words. Adapted from the Plectis site’s term previews
// (ai_workflow sites/microcosm/assets/docs.js showTip/hideTip/placeFloater and
// style.css .term-tip): prose uses a plain name; hovering, focusing or tapping
// it opens one shared card with the exact identifier and where it lives.
// The card is dismissible (Esc), hoverable and persistent (WCAG 1.4.13); the
// first mention on a page carries a dotted underline, repeats carry none.

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { href, onLinkClick } from "../app/router";
import { GLOSSARY, type GlossaryEntry } from "../app/glossary";
import { SymbolId } from "./parts";

interface TipState {
  entry: GlossaryEntry;
  anchor: HTMLElement;
  pinned: boolean;
}

const TipContext = createContext<{
  show: (id: string, anchor: HTMLElement, pinned: boolean) => void;
  hideSoon: () => void;
  hideNow: () => void;
  current: string | null;
} | null>(null);

export function TermProvider({ children }: { children: ReactNode }) {
  const [tip, setTip] = useState<TipState | null>(null);
  const timer = useRef(0);
  const card = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number; above: boolean } | null>(null);

  const show = useCallback((id: string, anchor: HTMLElement, pinned: boolean) => {
    const entry = GLOSSARY[id];
    if (!entry) return;
    window.clearTimeout(timer.current);
    setTip((t) => (t && t.anchor === anchor && t.pinned && !pinned ? t : { entry, anchor, pinned }));
  }, []);
  const hideNow = useCallback(() => {
    window.clearTimeout(timer.current);
    setTip(null);
  }, []);
  const hideSoon = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setTip((t) => (t?.pinned ? t : null)), 140);
  }, []);

  // Place the card beside the word: below it when there is room, otherwise above, never off screen.
  useEffect(() => {
    if (!tip || !card.current) return setPos(null);
    const place = () => {
      const r = tip.anchor.getBoundingClientRect();
      const c = card.current!.getBoundingClientRect();
      const edge = 8;
      const left = Math.min(Math.max(edge, r.left), window.innerWidth - c.width - edge);
      const below = r.bottom + 8;
      const above = r.top - 8 - c.height;
      const useAbove = below + c.height > window.innerHeight - edge && above > edge;
      setPos({ left, top: useAbove ? above : below, above: useAbove });
    };
    place();
    window.addEventListener("scroll", place, { passive: true });
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place);
      window.removeEventListener("resize", place);
    };
  }, [tip]);

  useEffect(() => {
    if (!tip) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        tip.anchor.focus();
        hideNow();
      }
    };
    const onDown = (e: PointerEvent) => {
      if (!card.current?.contains(e.target as Node) && !tip.anchor.contains(e.target as Node)) hideNow();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [tip, hideNow]);

  const e = tip?.entry;
  return (
    <TipContext.Provider value={{ show, hideSoon, hideNow, current: tip ? tip.entry.id : null }}>
      {children}
      {e ? (
        <div
          ref={card}
          id="term-tip"
          role="tooltip"
          className="term-tip"
          data-placement={pos?.above ? "above" : "below"}
          style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: 0 }}
          onPointerEnter={() => window.clearTimeout(timer.current)}
          onPointerLeave={hideSoon}
        >
          <p className="term-tip__label">{e.label}</p>
          <p className="term-tip__text">{e.text}</p>
          {e.identifier ? (
            <p className="term-tip__id">
              <span className="term-tip__key">{e.identifierLabel ?? "Exact name"}</span>
              <SymbolId id={e.identifier} />
            </p>
          ) : null}
          {e.where ? (
            <p className="term-tip__where">
              <span className="term-tip__key">Where</span>
              <SymbolId id={e.where} />
            </p>
          ) : null}
          {e.span || e.external ? (
            <p className="term-tip__actions">
              {e.span ? (
                <a href={href({ view: "source", span: e.span })} onClick={(ev) => { hideNow(); onLinkClick(ev); }}>
                  {e.span.startsWith("call:") ? "Open call site" : "Open definition"}
                </a>
              ) : null}
              {e.external ? (
                <a href={e.external} target="_blank" rel="noreferrer">
                  Read about it on another site&nbsp;↗
                </a>
              ) : null}
            </p>
          ) : null}
          <p className="term-tip__escape">Esc to close</p>
        </div>
      ) : null}
    </TipContext.Provider>
  );
}

const seen = new Set<string>();

/** A glossary word in prose or a table cell. */
export function Term({ id, children }: { id: string; children: ReactNode }) {
  const ctx = useContext(TipContext);
  const [first] = useState(() => {
    const isFirst = !seen.has(id);
    seen.add(id);
    return isFirst;
  });
  useEffect(() => () => void seen.delete(id), [id]);
  if (!ctx || !GLOSSARY[id]) return <>{children}</>;
  return (
    <button
      type="button"
      className={`term ${first ? "term--first" : ""}`}
      aria-describedby={ctx.current === id ? "term-tip" : undefined}
      onPointerEnter={(e) => e.pointerType === "mouse" && ctx.show(id, e.currentTarget, false)}
      onPointerLeave={(e) => e.pointerType === "mouse" && ctx.hideSoon()}
      onFocus={(e) => ctx.show(id, e.currentTarget, false)}
      onBlur={ctx.hideSoon}
      onClick={(e) => ctx.show(id, e.currentTarget, true)}
    >
      {children}
    </button>
  );
}
