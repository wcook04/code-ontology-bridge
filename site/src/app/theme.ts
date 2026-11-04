// Day and night schemes, adapted from lean-exposition/site/src/app/theme.ts.
// A stored choice is kept only when it differs from the system's, so choosing
// the system's own scheme follows the system again.

export type Scheme = "light" | "dark";
const KEY = "cob-theme";

export function systemScheme(): Scheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function currentScheme(): Scheme {
  const forced = document.documentElement.getAttribute("data-theme");
  return forced === "light" || forced === "dark" ? forced : systemScheme();
}

export function setScheme(next: Scheme): void {
  const root = document.documentElement;
  root.classList.add("no-transitions");
  try {
    if (next === systemScheme()) {
      root.removeAttribute("data-theme");
      localStorage.removeItem(KEY);
    } else {
      root.setAttribute("data-theme", next);
      localStorage.setItem(KEY, next);
    }
  } catch {
    if (next === systemScheme()) root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", next);
  }
  document.dispatchEvent(new CustomEvent("cob:scheme"));
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("no-transitions")));
}

export function onSchemeChange(listener: () => void): () => void {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  document.addEventListener("cob:scheme", listener);
  media.addEventListener("change", listener);
  return () => {
    document.removeEventListener("cob:scheme", listener);
    media.removeEventListener("change", listener);
  };
}
