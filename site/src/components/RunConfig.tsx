// The recorded run's setup, from examples/auto-ontology/live/current/manifest.json
// and RESULTS.md, so a reader can attribute each result to the right component.

import { Out } from "./parts";

const REPO = "https://github.com/wcook04/code-ontology-bridge/blob/main/examples/auto-ontology/live";

export function RunConfig() {
  return (
    <table className="rows config">
      <caption>How the run was set up</caption>
      <tbody>
        <tr>
          <th scope="row">Agent system</th>
          <td>NVIDIA Auto Ontology at commit <code>cdaf61e</code>, with a twelve-file patch for public model APIs, the SQL-only chat route and placeholder-answer validation</td>
        </tr>
        <tr>
          <th scope="row">Language model</th>
          <td>DeepSeek v4.1 Flash (<code>deepseek-v4.1-flash-1017</code>) through OpenRouter, not an NVIDIA model</td>
        </tr>
        <tr>
          <th scope="row">Retrieval models</th>
          <td>NVIDIA <code>nemotron-3-embed-1b</code> for embeddings and <code>llama-nemotron-rerank-vl-1b-v2</code> for reranking</td>
        </tr>
        <tr>
          <th scope="row">Questions</th>
          <td>The 22 development questions, written by the author while building the project; each names its output columns and 18 include a hint. The 16 held-out questions are on the comparison page.</td>
        </tr>
        <tr>
          <th scope="row">Scoring</th>
          <td>A program compared returned rows with rows from the author’s reference SQL. The run went once, start to finish; no question was asked again.</td>
        </tr>
        <tr>
          <th scope="row">Time per request</th>
          <td>Median 175 seconds, from 72 to 568, with three requests running at a time on a laptop that was running a second Auto Ontology instance alongside</td>
        </tr>
        <tr>
          <th scope="row">Not measured</th>
          <td>Cost, and which table descriptions each question retrieved. What the table descriptions and Auto Ontology each add is measured on the comparison page.</td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <td colSpan={2} className="small">
            Sources: <Out href={`${REPO}/current/manifest.json`}>run manifest</Out>, <Out href={`${REPO}/RESULTS.md`}>results</Out>,{" "}
            <Out href={`${REPO}/upstream-fix/README.md`}>patch description</Out>
          </td>
        </tr>
      </tfoot>
    </table>
  );
}
