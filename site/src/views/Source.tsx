// One verified source excerpt, opened from the example. Back returns to the
// exact place in the example, with the same graph view and selection.

import type { SourceStep, Walkthrough } from "../data/types";
import { useRoute } from "../data/useRoute";
import { Excerpt, Gate, Out } from "../components/parts";
import { back } from "../app/router";
import { roleOf } from "../app/roles";

export function Source({ spanId }: { spanId: string }) {
  const loaded = useRoute<Walkthrough>("/api/v1/walkthroughs/caller-chain-q11");
  return (
    <article className="band page" aria-labelledby="src-title">
      <nav className="crumbs" aria-label="Back">
        <button type="button" className="link-button" onClick={() => back("#/walkthrough/source")}>
          ← Back to the example
        </button>
      </nav>
      <Gate loaded={loaded} what="the source excerpt">
        {(w) => {
          const source = w.steps.find((s) => s.id === "source")?.data as SourceStep | undefined;
          const span = source?.spans.find((s) => s.id === spanId);
          if (!span) {
            return (
              <div className="gate gate--error" role="alert">
                <p>
                  <strong>This source excerpt is not part of the publication.</strong> The address names <code>{spanId}</code>.
                </p>
              </div>
            );
          }
          const isCall = span.kind === "call";
          const owner = span.record_id.includes("::") ? span.record_id : null;
          return (
            <>
              <p className="kicker">{isCall ? "Call site" : `Definition of the ${owner ? roleOf(owner).toLowerCase() : "symbol"}`}</p>
              <h1 id="src-title">
                <code className="wrap-id">{span.path}</code>
              </h1>
              <p>
                {isCall
                  ? `Line ${span.line_start}: the occurrence the extractor recorded.`
                  : `Lines ${span.line_start}–${span.line_end}. The excerpt shows where the definition starts.`}
              </p>
              <Excerpt text={span.excerpt} start={span.excerpt_line_start} mark={[span.line_start]} label={`${span.path} excerpt`} />
              <p className="small muted">
                From <code>{span.repository.replace("https://github.com/", "")}</code> at commit <code>{span.commit.slice(0, 12)}</code>.{" "}
                {span.excerpt_status === "verified_file_hash"
                  ? "The whole file’s SHA-256 matched the hash recorded in the extracted dataset before this excerpt was published."
                  : `Excerpt status: ${span.excerpt_status}.`}
              </p>
              <p>
                <Out href={span.source_url}>Open this line on GitHub at the pinned commit</Out>
              </p>
            </>
          );
        }}
      </Gate>
    </article>
  );
}
