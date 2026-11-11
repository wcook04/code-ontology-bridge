// The study's headline comparison on the first screen: the twelve questions about Auto
// Ontology's own code, inside Auto Ontology and asked directly. Every figure and every
// tile is computed from study/summary.json; nothing is shown in its place if that file
// fails to load.

import { onLinkClick } from "../app/router";
import { useStudy, type Cell, type StudySummary } from "../views/Study";

const MODEL = "deepseek";
const REPO = "auto_ontology";

function mean(v: number[]): number {
  return v.reduce((a, b) => a + b, 0) / v.length;
}

function list(v: number[]): string {
  return v.length > 1 ? `${v.slice(0, -1).join(", ")} and ${v[v.length - 1]}` : String(v[0] ?? "");
}

const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

function Line({ data, arm, label, note, score, count }: { data: StudySummary; arm: string; label: string; note: string; score: number; count: number }) {
  const rates = data.per_question_suite_rate[`${MODEL}/${arm}`] ?? {};
  const questions = data.question_list.filter((q) => q.repo === REPO);
  return (
    <div className="score__line">
      <p className="score__label">{label}</p>
      <p className="score__figure">
        <strong>{score.toFixed(1)}</strong> <span>of {count}</span>
      </p>
      <ol className="score__tiles" aria-hidden="true">
        {questions.map((q) => (
          <li key={q.id}>
            <span style={{ height: `${Math.round((rates[q.id] ?? 0) * 100)}%` }} />
          </li>
        ))}
      </ol>
      <p className="score__note">{note}</p>
    </div>
  );
}

export function ScoreCard() {
  const data = useStudy();
  if (data === null) return <aside className="score score--wait" role="status">Loading the study’s figures…</aside>;
  if (data === "error") {
    return (
      <aside className="score score--wait" role="alert">
        The study’s figures could not be loaded. <a href="#/study" onClick={onLinkClick}>The study page</a> reads the same file.
      </aside>
    );
  }
  const cell = (arm: string): Cell | undefined => data.cells.find((c) => c.model === MODEL && c.arm === arm);
  const inside = cell("C-native");
  const direct = cell("A");
  const directScore = direct?.suite_per_repo_mean?.[REPO];
  if (!inside || !direct || directScore === undefined) return null;
  const count = data.question_list.filter((q) => q.repo === REPO).length;
  return (
    <aside className="score" aria-labelledby="score-title">
      <h2 id="score-title" className="score__title">
        {count} questions about Auto Ontology’s own code, answered with DeepSeek v4.1 Flash
      </h2>
      <Line
        data={data}
        arm="C-native"
        label="Inside NVIDIA Auto Ontology, given only the code database"
        note={`Correct answers, mean of ${WORDS[inside.repetitions] ?? inside.repetitions} runs: ${list(inside.suite)}.`}
        score={mean(inside.suite)}
        count={count}
      />
      <Line
        data={data}
        arm="A"
        label="The same model asked directly, given table names only"
        note={`Correct answers, mean of ${WORDS[direct.repetitions] ?? direct.repetitions} runs.`}
        score={directScore}
        count={count}
      />
      <p className="score__foot">
        A tile is one question, filled by the share of runs that answered it correctly. The two rows compare complete setups: Auto
        Ontology’s agent adds retrieval, validation and repair of failed queries. AI models wrote the questions, and 21 of the 48 answer
        keys were corrected after the runs.{" "}
        <a href="#/study" onClick={onLinkClick}>
          Every setting, question and saved answer
        </a>
      </p>
    </aside>
  );
}
