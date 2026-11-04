// The comparison's held-out result, stated on the first screen. It reads the same
// experiment/summary.json as the comparison page and shows nothing until that file exists.

import { useEffect, useState } from "react";
import { onLinkClick } from "../app/router";

interface RunRow { model: string; arm: string; set: string; questions: number; expected_rows: number; median_seconds: number | null }

const ARM_WORDS: Record<string, string> = {
  schema: "given the schema alone",
  schema_model: "given the schema and this project’s semantic model",
  auto_ontology: "inside Auto Ontology, with this project’s model imported",
};
const MODEL_NAMES: Record<string, string> = { nemotron: "NVIDIA Nemotron 3.5 Lightning", deepseek: "DeepSeek v4.1 Flash" };

export function HeadlineResult() {
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  useEffect(() => {
    fetch(new URL("experiment/summary.json", document.baseURI)).then(
      (r) => (r.ok ? r.json().then((d) => setRuns(d.runs)) : undefined),
      () => undefined,
    );
  }, []);
  if (!runs) return null;
  const model = runs.some((r) => r.model === "nemotron" && r.set === "heldout") ? "nemotron" : "deepseek";
  const held = ["schema", "schema_model", "auto_ontology"].map((arm) => runs.find((r) => r.model === model && r.arm === arm && r.set === "heldout"));
  if (held.some((r) => !r)) return null;
  return (
    <div className="headline-cmp">
      <p className="headline-cmp__lead">
        On {held[0]!.questions} held-out questions about Auto Ontology’s own code, {MODEL_NAMES[model]} returned exactly the right rows:
      </p>
      <ul className="headline-cmp__list">
        {held.map((r) => (
          <li key={r!.arm}>
            <strong>
              {r!.expected_rows} of {r!.questions}
            </strong>{" "}
            {ARM_WORDS[r!.arm]}
          </li>
        ))}
      </ul>
      <p className="small">
        <a href="#/comparison" onClick={onLinkClick}>
          See both models, both question sets and every question
        </a>
      </p>
    </div>
  );
}
