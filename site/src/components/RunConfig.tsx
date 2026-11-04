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
          <td>NVIDIA Auto Ontology at commit <code>cdaf61e</code>, with a twelve-file patch for public model APIs and the SQL-only chat route</td>
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
          <td>22, written by the author during development; each names its output columns and 18 include a hint</td>
        </tr>
        <tr>
          <th scope="row">Scoring</th>
          <td>A program compared returned rows with rows from the author’s reference SQL; the author read every response</td>
        </tr>
        <tr>
          <th scope="row">Time per request</th>
          <td>Median 146 seconds, from 50 to 274, with three requests running at a time</td>
        </tr>
        <tr>
          <th scope="row">Not measured</th>
          <td>Accuracy on new questions, the effect of the semantic model against a schema-only agent, cost, and which table descriptions each question retrieved</td>
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
