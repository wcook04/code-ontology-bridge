import { useEffect, useRef, useState } from "react";
import { parse, useHash, onLinkClick } from "./router";
import { currentScheme, onSchemeChange, setScheme, type Scheme } from "./theme";
import { FAMILY } from "./family";
import { loadPublication, type Publication } from "../data/client";
import { Home } from "../views/Home";
import { Outcomes } from "../views/Outcomes";
import { Question } from "../views/Question";
import { Source } from "../views/Source";
import { Out } from "../components/parts";
import { TermProvider } from "../components/Term";

const REPO = "https://github.com/wcook04/code-ontology-bridge";
// Both links name the exact commit this website was built from, so the paper and code match the deployed pages.
const COMMIT = typeof __SOURCE_COMMIT__ === "string" && __SOURCE_COMMIT__ ? __SOURCE_COMMIT__ : "codex/paper-and-diagrams";
const PAPER = `${REPO}/blob/${COMMIT}/docs/case-study.pdf`;
const CODE = `${REPO}/tree/${COMMIT}`;

export function App() {
  const hash = useHash();
  const route = parse(hash);
  const [pub, setPub] = useState<Publication | null>(null);
  const main = useRef<HTMLElement>(null);
  const lastView = useRef<string | null>(null);

  useEffect(() => {
    loadPublication().then(setPub, () => undefined);
  }, []);

  // Move focus to the page on navigation between views, so keyboard and screen reader users start at the top of the new view.
  const viewKey = route.view === "home" ? "home" : hash.split("?")[0];
  useEffect(() => {
    const previous = lastView.current;
    lastView.current = viewKey;
    if (previous === null || previous === viewKey) return;
    main.current?.focus({ preventScroll: true });
  }, [viewKey]);

  useEffect(() => {
    const titles: Record<string, string> = {
      home: "Code Ontology Bridge: make a Python repository queryable by a SQL agent",
      outcomes: "The 22 recorded questions | Code Ontology Bridge",
      question: route.view === "question" ? `Question ${route.id} | Code Ontology Bridge` : "",
      source: "Source excerpt | Code Ontology Bridge",
      missing: "Page not found | Code Ontology Bridge",
    };
    document.title = titles[route.view];
  }, [route]);

  return (
    <TermProvider>
      <Header current={route.view} />
      <main id="main" ref={main} tabIndex={-1}>
        {route.view === "home" ? <Home key="home" stepTarget={route.step} /> : null}
        {route.view === "outcomes" ? <Outcomes params={route.params} /> : null}
        {route.view === "question" ? <Question key={route.id} id={route.id} total={pub?.manifest.question_count ?? 22} /> : null}
        {route.view === "source" ? <Source spanId={route.span} /> : null}
        {route.view === "missing" ? (
          <section className="band page">
            <h1>Nothing at this address</h1>
            <p>
              <code>{route.hash}</code> does not name a page here. <a href="#/" onClick={onLinkClick}>Go to the caller example</a> or{" "}
              <a href="#/outcomes" onClick={onLinkClick}>all 22 questions</a>.
            </p>
          </section>
        ) : null}
      </main>
      <Footer pub={pub} />
    </TermProvider>
  );
}

function Header({ current }: { current: string }) {
  const [scheme, setLocal] = useState<Scheme>(currentScheme());
  useEffect(() => onSchemeChange(() => setLocal(currentScheme())), []);
  return (
    <header className="topbar">
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        Skip to content
      </a>
      <div className="topbar__inner">
        <span className="fam-lockup">
          <a className="fam-lockup__home" href={FAMILY.owner.home} rel="author" title="All of Will Cook’s websites and films">
            <img src={`${import.meta.env.BASE_URL}plectis.svg`} alt="Will Cook: all websites and films" width={26} height={26} />
          </a>
          <span className="fam-lockup__rule" aria-hidden="true" />
          <a className="fam-lockup__site" href="#/" onClick={onLinkClick} aria-current={current === "home" ? "page" : undefined}>
            <svg viewBox="0 0 32 32" aria-hidden="true" className="fam-mark">
              <path className="fam-mark__ink" d="M5 9h9M5 16h6M5 23h9" />
              <path className="fam-mark__warm" d="M17 9c6 0 6 14 0 14" strokeDasharray="2.5 2.5" />
              <circle className="fam-mark__cool-fill" cx="26" cy="16" r="3" />
            </svg>
            <span className="fam-lockup__name" translate="no">
              Code Ontology Bridge
            </span>
          </a>
        </span>
        <nav className="topnav" aria-label="Site">
          <a href="#/walkthrough/source" onClick={onLinkClick} aria-current={current === "home" ? "page" : undefined}>
            Caller example
          </a>
          <a href="#/outcomes" onClick={onLinkClick} aria-current={current === "outcomes" || current === "question" ? "page" : undefined}>
            22 questions
          </a>
          <Out href={PAPER}>Paper</Out>
          <Out href={CODE}>Code</Out>
          <button
            type="button"
            className="scheme"
            aria-label={scheme === "dark" ? "Switch to the light scheme" : "Switch to the dark scheme"}
            onClick={() => setScheme(scheme === "dark" ? "light" : "dark")}
          >
            <svg viewBox="0 0 20 20" aria-hidden="true" width="18" height="18">
              {scheme === "dark" ? (
                <circle cx="10" cy="10" r="4" fill="currentColor" />
              ) : (
                <path d="M14.5 12.5A6 6 0 0 1 7.5 5.5a6 6 0 1 0 7 7z" fill="currentColor" />
              )}
            </svg>
          </button>
        </nav>
      </div>
    </header>
  );
}

function Footer({ pub }: { pub: Publication | null }) {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div className="footer__about">
          <p>
            <strong translate="no">code-ontology-bridge</strong> is an independent Python-source adapter for{" "}
            <Out href="https://github.com/NVIDIA/auto-ontology">NVIDIA Auto Ontology</Out>, made by Will Cook. It is not affiliated with or endorsed by NVIDIA.
          </p>
          <p className="small muted">
            Every page reads a static publication of the recorded run:{" "}
            <a href="./data/index.json">data/index.json</a>
            {pub ? (
              <>
                , publication <code>{pub.manifest.publication_sha256.slice(0, 12)}</code>, built from source commit{" "}
                <code>{pub.entry.source_commit.slice(0, 12)}</code>
              </>
            ) : null}
            . <Out href={PAPER}>Paper (PDF)</Out>, <Out href={CODE}>source code</Out>, <Out href={`${REPO}/blob/main/docs/inspection-api.md`}>API and local server</Out>
          </p>
        </div>
        <nav className="fam-sites" aria-label={`${FAMILY.owner.name}'s websites`}>
          <p className="fam-sites__title">More from {FAMILY.owner.name}</p>
          <ul className="fam-sites__list">
            {FAMILY.sites.map((site) => (
              <li key={site.id}>
                <a href={site.url}>{site.short}</a>
              </li>
            ))}
            <li>
              <a href={FAMILY.owner.home}>All websites and films</a>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
