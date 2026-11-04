// Addresses live after the # so the site works from any folder on a static host.
//   #/                         the caller example (and #/walkthrough/<step> for one step)
//   #/outcomes?table=fail      all 22 recorded outcomes, with optional filters
//   #/questions/14             one recorded question
//   #/source/<span id>         one verified source excerpt
//
// History follows Proof Reader's rule (web/src/app/history.ts): opening something
// pushes an entry; changing a view inside a page only rewrites the entry it is in.
// Each entry keeps the page's scroll position and its view state, so Back lands
// where the reader stood.

import { useSyncExternalStore } from "react";

export type Route =
  | { view: "home"; step?: string }
  | { view: "outcomes"; params: URLSearchParams }
  | { view: "question"; id: number }
  | { view: "source"; span: string }
  | { view: "missing"; hash: string };

export interface EntryState {
  scrollY?: number;
  /** View state owned by the page (graph preset, selected node, SQL layout). */
  view?: Record<string, unknown>;
  /** Set on entries the site pushed, so "Back" can use history safely. */
  internal?: boolean;
}

function decode(part: string): string {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

export function parse(hash: string): Route {
  const raw = hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?", 2);
  const parts = path.split("/").filter(Boolean);
  if (parts.length === 0) return { view: "home" };
  if (parts[0] === "walkthrough" && parts.length === 2) return { view: "home", step: decode(parts[1]) };
  if (parts[0] === "outcomes" && parts.length === 1) return { view: "outcomes", params: new URLSearchParams(query) };
  if (parts[0] === "questions" && parts.length === 2 && /^\d+$/.test(parts[1])) return { view: "question", id: Number(parts[1]) };
  if (parts[0] === "source" && parts.length >= 2) return { view: "source", span: decode(parts.slice(1).join("/")) };
  return { view: "missing", hash };
}

export function href(route: Route): string {
  switch (route.view) {
    case "home":
      return route.step ? `#/walkthrough/${encodeURIComponent(route.step)}` : "#/";
    case "outcomes": {
      const q = route.params.toString();
      return q ? `#/outcomes?${q}` : "#/outcomes";
    }
    case "question":
      return `#/questions/${route.id}`;
    case "source":
      return `#/source/${encodeURIComponent(route.span)}`;
    case "missing":
      return route.hash;
  }
}

const listeners = new Set<() => void>();
let snapshot = window.location.hash;

function notify(): void {
  snapshot = window.location.hash;
  for (const listener of listeners) listener();
}

window.addEventListener("popstate", notify);
window.addEventListener("hashchange", notify);
if ("scrollRestoration" in history) history.scrollRestoration = "manual";

export function useHash(): string {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => snapshot,
  );
}

export function entryState(): EntryState {
  const state = history.state as EntryState | null;
  return state && typeof state === "object" ? state : {};
}

/** Rewrite the current entry: a view change inside the page, never a new Back step. */
export function replaceView(view: Record<string, unknown>, url?: string): void {
  try {
    history.replaceState({ ...entryState(), view: { ...entryState().view, ...view } }, "", url);
    if (url) notify();
  } catch {
    /* a sandboxed frame: the next write carries the same facts */
  }
}

/** Open something: remember where the reader stood, then push the new address. */
export function navigate(url: string): void {
  if (url === window.location.hash) return;
  try {
    history.replaceState({ ...entryState(), scrollY: window.scrollY }, "");
  } catch {
    /* see above */
  }
  history.pushState({ internal: true } satisfies EntryState, "", url);
  notify();
}

/** Go back if the previous entry is one of ours; otherwise open the fallback address. */
export function back(fallback: string): void {
  if (entryState().internal) history.back();
  else {
    history.replaceState({}, "", fallback);
    notify();
  }
}

/** Ordinary link clicks inside the site go through navigate(), so scroll is kept. */
export function onLinkClick(event: React.MouseEvent<HTMLAnchorElement>): void {
  const anchor = event.currentTarget;
  const target = anchor.getAttribute("href") ?? "";
  if (!target.startsWith("#/") || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  navigate(target);
}
