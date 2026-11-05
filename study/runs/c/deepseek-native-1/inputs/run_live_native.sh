#!/bin/sh
# Run NVIDIA Auto Ontology natively on this machine (no Docker) and load our code
# ontology into it through its own entry points, saving every request and response.
#
# Usage:
#   sh examples/auto-ontology/live/run_live.sh [--with-key ENV_FILE]
#
# Environment:
#   AUTO_ONTOLOGY_CLONE  clone of NVIDIA/auto-ontology (default: the annex clone below)
#   PG_BIN               PostgreSQL 17 bin dir with pg_trgm and pgvector
#                        (default: Homebrew postgresql@17; `brew install postgresql@17 pgvector`)
#   PG_PORT              default 54329
#
# Without --with-key every step runs with no model key (steps 1-7 plus the
# keyless probes 8 and 9). With --with-key ENV_FILE, step 10 reads NVIDIA_API_KEY
# from ENV_FILE into the environment of their backend and ingestion processes
# only. The value is never printed, logged or written; this script never echoes it.
#
# AO_RUN_DIR must name a new absolute output directory. Captures and the
# disposable PostgreSQL cluster are isolated there; existing runs are never reset.
# AO_BACKEND_PORT, AO_KEYLESS_PORT and AO_INGEST_PORT select service ports.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
EX="$(cd "$HERE/.." && pwd)"
CLONE="${AUTO_ONTOLOGY_CLONE:?set AUTO_ONTOLOGY_CLONE to a checkout of NVIDIA/auto-ontology}"
PG_BIN="${PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
PG_PORT="${PG_PORT:-54329}"
PY="$REPO/.venv/bin/python"
COB="$REPO/.venv/bin/cob"
DB1=auto_ontology        # step 2-3, 6-7: model import onto an empty store
DB2=auto_ontology_g10    # step 4-5, 8-9: DuckDB source connected first, then import
DB3=auto_ontology_keyed  # step 10 (only with --with-key)
BACKEND_PORT=${AO_BACKEND_PORT:-3011}
KEYLESS_PORT=${AO_KEYLESS_PORT:-3001}
INGEST_PORT=${AO_INGEST_PORT:-3002}
B1=http://127.0.0.1:$KEYLESS_PORT
B2=http://127.0.0.1:$BACKEND_PORT
MODEL_FILE="${AO_MODEL_FILE:-$EX/auto_ontology_code.model.yaml}"
EVALUATION_FILE="${AO_EVALUATION_FILE:-$EX/auto_ontology_code/evaluation.json}"
KEY_FILE=""
if [ "${1:-}" = "--with-key" ]; then KEY_FILE="${2:?--with-key needs an env file path}"; fi

RUN_ROOT="${AO_RUN_DIR:?set AO_RUN_DIR to a new, absolute output directory}"
case "$RUN_ROOT" in /*) ;; *) echo "AO_RUN_DIR must be absolute" >&2; exit 2 ;; esac
[ ! -e "$RUN_ROOT" ] || { echo "refusing to overwrite existing AO_RUN_DIR" >&2; exit 2; }
mkdir -p "$RUN_ROOT"
PGDATA="$RUN_ROOT/.pgdata"
RESP="$RUN_ROOT/responses"
LOGS="$RUN_ROOT/logs"
WORK="$RUN_ROOT/.work"
CERT="$RUN_ROOT/cert"
PIDS=""

say() { printf '\n== %s\n' "$*"; }
psql_db() { _pgdb="$1"; shift; "$PG_BIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U postgres -d "$_pgdb" -v ON_ERROR_STOP=1 "$@"; }
cap() { "$PY" "$HERE/capture.py" "$@" || true; }
cap_required() { "$PY" "$HERE/capture.py" "$@"; }

cleanup() {
  for p in $PIDS; do kill "$p" 2>/dev/null || true; done
  sleep 2
  for p in $PIDS; do kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null || true; done
  if [ -f "$PGDATA/postmaster.pid" ]; then LC_ALL=en_US.UTF-8 "$PG_BIN/pg_ctl" -D "$PGDATA" -m fast stop >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

ao_env() {
  # Postgres settings for their processes. Trust auth on 127.0.0.1, so the
  # password is a placeholder their code requires to be set, not a secret.
  POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="$PG_PORT" POSTGRES_USER=postgres \
  POSTGRES_PASSWORD=trust-auth-placeholder POSTGRES_DATABASE="$1"
  INGESTION_SERVICE_URL="http://127.0.0.1:$INGEST_PORT"
  export POSTGRES_HOST POSTGRES_PORT POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DATABASE INGESTION_SERVICE_URL
}

key_env() {
  # Only ever called inside the subshell that execs one of their processes, so
  # the key exists in that process's environment and nowhere else.
  NVIDIA_API_KEY="$(grep -E '^NVIDIA_API_KEY=' "$KEY_FILE" | head -1 | cut -d= -f2- | tr -d "\"'")"
  DEFAULT_MODELS_ENDPOINT=https://integrate.api.nvidia.com/v1
  DEFAULT_MODELS_MODEL="${AO_CHAT_MODEL:-nvidia/nemotron-3-nano-30b-a3b}"  # their .env.example default; see RESULTS.md
  EMBED_ENDPOINT=https://integrate.api.nvidia.com/v1
  EMBED_MODEL=nvidia/nemotron-3-embed-1b
  RERANK_ENDPOINT=https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-vl-1b-v2/reranking
  RERANK_MODEL=nvidia/llama-nemotron-rerank-vl-1b-v2
  export NVIDIA_API_KEY DEFAULT_MODELS_ENDPOINT DEFAULT_MODELS_MODEL EMBED_ENDPOINT EMBED_MODEL RERANK_ENDPOINT RERANK_MODEL
  # Optional: send chat (reasoning and non-reasoning roles) to another
  # OpenAI-compatible endpoint, keeping NVIDIA embeddings and reranking.
  # AO_CHAT_KEY_VAR names the variable in KEY_FILE that holds that endpoint's key.
  if [ -n "${AO_CHAT_ENDPOINT:-}" ]; then
    REASONING_API_KEY="$(grep -E "^${AO_CHAT_KEY_VAR:?set AO_CHAT_KEY_VAR}=" "$KEY_FILE" | head -1 | cut -d= -f2- | tr -d "\"'")"
    NON_REASONING_API_KEY="$REASONING_API_KEY"
    REASONING_ENDPOINT="$AO_CHAT_ENDPOINT"; NON_REASONING_ENDPOINT="$AO_CHAT_ENDPOINT"
    REASONING_MODEL="$AO_CHAT_MODEL"; NON_REASONING_MODEL="$AO_CHAT_MODEL"
    REASONING_CLIENT=openai; NON_REASONING_CLIENT=openai
    export REASONING_API_KEY NON_REASONING_API_KEY REASONING_ENDPOINT NON_REASONING_ENDPOINT REASONING_MODEL NON_REASONING_MODEL REASONING_CLIENT NON_REASONING_CLIENT
  fi
}

start_backend() { # db port log [connection_string] ; uses the key when USE_KEY=1
  ( cd "$CLONE" && ao_env "$1" && { [ -z "${4:-}" ] || { CONNECTION_STRINGS="$4"; export CONNECTION_STRINGS; }; } \
      && { [ "${USE_KEY:-0}" != 1 ] || key_env; } \
      && exec .venv/bin/python -m uvicorn auto_ontology.server.__main__:create_app --factory --host 127.0.0.1 --port "$2" ) > "$3" 2>&1 &
  PIDS="$PIDS $!"
  i=0; until curl -sf -o /dev/null "http://127.0.0.1:$2/api/health/live"; do i=$((i+1)); [ $i -gt 90 ] && { echo "backend on $2 did not start"; tail -20 "$3"; exit 1; }; sleep 1; done
}

start_ingestion() { # db log ; uses the key when USE_KEY=1
  ( cd "$CLONE" && ao_env "$1" && { [ "${USE_KEY:-0}" != 1 ] || key_env; } \
      && CONNECTION_STRINGS="duckdb://$WORK/auto_ontology_code.duckdb" INGESTION_PORT="$INGEST_PORT" \
      exec .venv/bin/python -m auto_ontology.ingestion_service ) > "$2" 2>&1 &
  PIDS="$PIDS $!"
  i=0; until grep -q "ingest: next run at" "$2" 2>/dev/null; do i=$((i+1)); [ $i -gt 600 ] && { echo "ingestion did not finish its startup pass"; tail -30 "$2"; exit 1; }; sleep 1; done
}

stop_started() { for p in $PIDS; do kill "$p" 2>/dev/null || true; done; sleep 3; PIDS=""; }

# ---------------------------------------------------------------------------
say "0. setup: their venv, our DuckDB, Postgres 17 with pg_trgm + pgvector"
[ -d "$CLONE/auto_ontology" ] || { echo "no Auto Ontology clone at $CLONE"; exit 2; }
if [ "${AO_SKIP_SYNC:-0}" != 1 ]; then ( cd "$CLONE" && uv sync --frozen >/dev/null ); fi
[ -n "${AO_DUCKDB_FILE:-}" ] || [ -f "$EX/auto_ontology_code.duckdb" ] || AUTO_ONTOLOGY_CLONE="$CLONE" sh "$EX/reproduce.sh" "$CLONE"
mkdir -p "$RESP" "$LOGS" "$CERT" "$WORK"
git -C "$CLONE" rev-parse HEAD > "$RESP/00_auto_ontology_commit.txt"
git -C "$REPO" rev-parse HEAD > "$RESP/00_code_ontology_bridge_commit.txt"
"$PG_BIN/postgres" --version > "$RESP/00_postgres_version.txt"
# Our DuckDB is written by duckdb>=2.0.0; their pinned duckdb 1.5.5 cannot read
# that storage version. Make a v1.5.0-storage copy for their connector.
"$PY" "$HERE/make_compat_duckdb.py" "${AO_DUCKDB_FILE:-$EX/auto_ontology_code.duckdb}" "$WORK" > "$RESP/05a_compat_duckdb_copy.json"
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  "$PG_BIN/initdb" -D "$PGDATA" -U postgres --auth=trust -E UTF8 --locale=en_US.UTF-8 > "$LOGS/pg_initdb.log" 2>&1
fi
LC_ALL=en_US.UTF-8 "$PG_BIN/pg_ctl" -D "$PGDATA" -o "-p $PG_PORT -h 127.0.0.1 -k $PGDATA" -l "$LOGS/pg_server.log" -w start
for db in $DB1 $DB2; do
  psql_db postgres -q -c "DROP DATABASE IF EXISTS $db" -c "CREATE DATABASE $db"
  ( cd "$CLONE" && ao_env "$db" && uv run --no-sync alembic upgrade head ) > "$LOGS/alembic_$db.log" 2>&1
done

# ---------------------------------------------------------------------------
if [ -z "${KEYED_ONLY:-}" ]; then  # KEYED_ONLY=1 with --with-key runs only step 10
say "1. health (store $DB1)"
start_backend $DB1 "$KEYLESS_PORT" "$LOGS/backend_db1.log"
cap "$RESP/01_health.json" GET "$B1/api/health"

say "2. model import, replace=false, embed=false"
cap "$RESP/02_model_import.json" POST "$B1/api/model/import?replace=false&embed=false" \
  --body-file "$MODEL_FILE" --content-type application/x-yaml
cap "$RESP/02a_terms.json" GET "$B1/api/terms"
TID=$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1]))['response'];print([t['id'] for t in d['terms'] if t['name']=='Source file'][0])" "$RESP/02a_terms.json")
cap "$RESP/02b_term_source_file.json" GET "$B1/api/terms/$TID"
cap "$RESP/02c_term_source_file_column_attributes.json" GET "$B1/api/terms/$TID/column-attributes"
cap "$RESP/02d_semantic_graph.json" GET "$B1/api/exploration/semantic-graph"
cap "$RESP/02e_exploration_graph.json" GET "$B1/api/exploration/graph"
cap "$RESP/02f_exploration_edges.json" GET "$B1/api/exploration/edges"
cap "$RESP/02g_datasources_dbs.json" GET "$B1/api/datasources/dbs"
psql_db $DB1 -f "$HERE/sql/store_counts.sql" > "$RESP/02h_postgres_store_counts.txt"
psql_db $DB1 -c "SELECT source, count(*) FROM term GROUP BY 1" > "$RESP/02i_postgres_term_source.txt"
psql_db $DB1 -f "$HERE/sql/catalog_keys.sql" > "$RESP/02j_catalog_keys_after_import.txt"

say "3. G9: does any response body carry imported_id?"
"$PY" - "$RESP" > "$RESP/03_g9_imported_id_in_responses.json" <<'EOF'
import json, sys, pathlib
out = {}
for p in sorted(pathlib.Path(sys.argv[1]).glob("0[12]*.json")):
    out[p.name] = json.dumps(json.load(open(p))["response"]).count("imported_id")
print(json.dumps({"occurrences_in_response_bodies": out, "total": sum(out.values())}, indent=2))
EOF

say "6. read-only routes behind their MCP allow-list (mcp/auto_ontology_mcp/tools.py)"
TBL=$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1]))['response']['data'];t=d['tables'][0];print(t['id'] if isinstance(t,dict) else t)" "$RESP/02b_term_source_file.json")
cap "$RESP/06a_search_terms.json" GET "$B1/api/terms?query=symbol"
cap "$RESP/06b_get_term.json" GET "$B1/api/terms/$TID"
cap "$RESP/06c_get_term_columns.json" GET "$B1/api/terms/$TID/column-attributes"
cap "$RESP/06d_get_term_sql_attributes.json" GET "$B1/api/terms/$TID/sql-attributes"
cap "$RESP/06e_get_sql_attribute_missing.json" GET "$B1/api/sql-attributes/does-not-exist"
cap "$RESP/06f_describe_table.json" GET "$B1/api/exploration/tables/$TBL/details"
cap "$RESP/06g_readiness_status.json" GET "$B1/api/semantic-compilation/status"
cap "$RESP/06h_readiness_connections.json" GET "$B1/api/connections"
cap "$RESP/06i_check_answerable_no_key.json" POST "$B1/api/question-entity-coverage" --json '{"question":"Which functions call resolve_semantic_fks?"}'
cap "$RESP/06j_global_search.json" POST "$B1/api/search/global-search" --json '{"search_term":"symbol"}'

say "7. certification: certify -> plan -> PATCH, flags read back from Postgres"
psql_db $DB1 -At -c "SELECT coalesce(json_object_agg(imported_id, id), '{}') FROM (
  SELECT imported_id, id FROM term WHERE imported_id IS NOT NULL
  UNION ALL SELECT imported_id, id FROM column_attribute WHERE imported_id IS NOT NULL
  UNION ALL SELECT imported_id, id FROM sql_attribute WHERE imported_id IS NOT NULL) x" > "$CERT/id_map.json"
( cd "$REPO" && "$COB" certify --log "$CERT/events.jsonl" --targets "$HERE/cert_targets.json" --root examples/auto-ontology \
    --actor "live-run:code-ontology-bridge" --out "$CERT/certify_result.json" ) || true   # exits 1: one target fails by design
( cd "$REPO" && "$COB" cert-status --log "$CERT/events.jsonl" --root examples/auto-ontology --plan-patches \
    --id-map "$CERT/id_map.json" --out "$CERT/plan.json" )
( cd "$REPO" && env -u AUTO_ONTOLOGY_API_TOKEN "$COB" cert-status --log "$CERT/events.jsonl" --root examples/auto-ontology \
    --plan-patches --id-map "$CERT/id_map.json" --apply --base-url "$B1" --out "$CERT/apply_attempt.json" ) \
    > "$CERT/apply_attempt.stdout" 2>&1 || echo "cob --apply exit $? (expected: refuses without AUTO_ONTOLOGY_API_TOKEN)" >> "$CERT/apply_attempt.stdout"
psql_db $DB1 -f "$HERE/sql/cert_flags.sql" > "$RESP/07a_flags_before.txt"
"$PY" "$HERE/apply_plan_no_token.py" "$CERT/plan.json" "$B1" "$RESP/07c_patch_no_header" || true
psql_db $DB1 -f "$HERE/sql/cert_flags.sql" > "$RESP/07b_flags_after.txt"
"$PY" "$HERE/apply_plan_no_token.py" "$CERT/plan.json" "$B1" "$RESP/07d_patch_with_user_header" "live-run:code-ontology-bridge" || true
SYM=$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1]))['cob:auto_ontology_code:term:symbols'])" "$CERT/id_map.json")
cap "$RESP/07e_get_term_symbols_after.json" GET "$B1/api/terms/$SYM"

# ---------------------------------------------------------------------------
say "5. catalog ingestion of the DuckDB source (store $DB2, ingestion service, no key)"
start_ingestion $DB2 "$LOGS/ingestion_db2.log"
psql_db $DB2 -f "$HERE/sql/store_counts.sql" > "$RESP/05b_postgres_catalog_after_ingest.txt"
psql_db $DB2 -f "$HERE/sql/catalog_keys.sql" > "$RESP/05c_catalog_keys_after_ingest.txt"
grep -E "Data ingestion finished|Embed auto_ontology_code|AuthenticationError" "$LOGS/ingestion_db2.log" | cut -c1-300 > "$RESP/05d_ingestion_log_excerpt.txt" || true

say "4. G10: import our model onto the store where the DuckDB source is already connected"
start_backend $DB2 "$BACKEND_PORT" "$LOGS/backend_db2.log" "duckdb://$WORK/auto_ontology_code.duckdb"
cap "$RESP/04a_health_db2.json" GET "$B2/api/health"
cap "$RESP/04b_connections_test_duckdb.json" POST "$B2/api/connections/test" --json "{\"connection\":{\"type\":\"duckdb\",\"database\":\"$WORK/auto_ontology_code.duckdb\"}}"
cap "$RESP/04c_connections_source.json" GET "$B2/api/connections/source"
cap "$RESP/04d_datasources_dbs_before_import.json" GET "$B2/api/datasources/dbs"
cap "$RESP/04e_model_import_onto_connected_db.json" POST "$B2/api/model/import?replace=false&embed=false" \
  --body-file "$MODEL_FILE" --content-type application/x-yaml
grep -E "UniqueViolation|DETAIL:|model_interchange.py\", line" "$LOGS/backend_db2.log" | head -8 > "$RESP/04f_model_import_500_log_excerpt.txt" || true
psql_db $DB2 -f "$HERE/sql/store_counts.sql" > "$RESP/04g_postgres_after_failed_import.txt"
# Workaround test: give the catalog rows their live ids, keep cob: ids for terms.
psql_db $DB2 -At -f "$HERE/sql/live_catalog_ids.sql" > "$WORK/live_catalog_ids.json"
"$PY" "$HERE/remap_catalog_ids.py" "$MODEL_FILE" "$WORK/live_catalog_ids.json" "$WORK/model_remapped_to_live_catalog.yaml" > "$RESP/04h_remap_summary.json"
cap "$RESP/04i_model_import_remapped_to_live_catalog.json" POST "$B2/api/model/import?replace=false&embed=false" \
  --body-file "$WORK/model_remapped_to_live_catalog.yaml" --content-type application/x-yaml
psql_db $DB2 -f "$HERE/sql/store_counts.sql" > "$RESP/04j_postgres_after_remapped_import.txt"
psql_db $DB2 -f "$HERE/sql/catalog_keys.sql" >> "$RESP/04j_postgres_after_remapped_import.txt"

say "8. ask_question route with no key (plumbing only)"
"$PY" "$HERE/ask_questions.py" "$B2" "$EVALUATION_FILE" "$RESP/08_ask_no_key" 1 || true

say "9. semantic compilation with no key (flag off, then on)"
cap "$RESP/09a_semantic_compile_trigger_flag_off.json" POST "$B2/api/semantic-compilation/trigger" --json '{}'
sleep 3
psql_db $DB2 -q -f "$HERE/sql/frontend_configurations.sql"
cap "$RESP/09c_semantic_compile_trigger_flag_on_no_key.json" POST "$B2/api/semantic-compilation/trigger" --json '{}'
i=0; until grep -q "semantic: finished\|semantic: unhandled" "$LOGS/ingestion_db2.log"; do i=$((i+1)); [ $i -gt 120 ] && break; sleep 1; done
grep -E "REASONING_API_KEY|EMBED_API_KEY|semantic FK removed|Semantic FK edges created|semantic: finished|Unexpected error processing table" \
  "$LOGS/ingestion_db2.log" | cut -c1-300 > "$RESP/09e_compile_log_excerpt.txt" || true
psql_db $DB2 -f "$HERE/sql/store_counts.sql" > "$RESP/09d_postgres_after_compile_no_key.txt"

# ---------------------------------------------------------------------------
fi  # KEYED_ONLY
if [ -n "$KEY_FILE" ]; then
  say "10. WITH KEY (fresh store $DB3): ingest with embeddings, import, compile, ask"
  [ -f "$KEY_FILE" ] && grep -q '^NVIDIA_API_KEY=' "$KEY_FILE" || { echo "no NVIDIA_API_KEY line in $KEY_FILE"; exit 4; }
  stop_started
  psql_db postgres -q -c "DROP DATABASE IF EXISTS $DB3" -c "CREATE DATABASE $DB3"
  ( cd "$CLONE" && ao_env "$DB3" && uv run --no-sync alembic upgrade head ) > "$LOGS/alembic_$DB3.log" 2>&1
  psql_db $DB3 -q -f "$HERE/sql/frontend_configurations.sql"
  psql_db $DB3 -q -c "UPDATE frontend.configurations SET value='false' WHERE key='semantic_compilation_enabled'"
  USE_KEY=1
  start_ingestion $DB3 "$LOGS/ingestion_keyed.log"
  start_backend $DB3 "$BACKEND_PORT" "$LOGS/backend_keyed.log" "duckdb://$WORK/auto_ontology_code.duckdb"
  USE_KEY=0
  grep -E "Data ingestion finished|Embed auto_ontology_code" "$LOGS/ingestion_keyed.log" | cut -c1-300 > "$RESP/10a_ingest_log_excerpt.txt" || true
  echo "model import skipped (C-native)" > "$RESP/10c_model_import_skipped.txt"
  psql_db $DB3 -q -f "$HERE/sql/frontend_configurations.sql"
  : > "$LOGS/ingestion_keyed.compile_marker"
  cap_required "$RESP/10d_semantic_compile_trigger.json" POST "$B2/api/semantic-compilation/trigger" --json '{}'
  i=0; until grep -q "semantic: finished\|semantic: unhandled" "$LOGS/ingestion_keyed.log"; do
    i=$((i+1)); [ $i -gt 450 ] && { echo "compilation did not finish within 15 minutes"; exit 5; }; sleep 2
  done
  grep -q "semantic: finished successfully" "$LOGS/ingestion_keyed.log" || { echo "compilation failed"; exit 5; }
  cap_required "$RESP/10e_semantic_status.json" GET "$B2/api/semantic-compilation/status"
  cap "$RESP/10f_terms_after_compile.json" GET "$B2/api/terms"
  psql_db $DB3 -f "$HERE/sql/store_counts.sql" > "$RESP/10g_postgres_after_compile.txt"
  cap "$RESP/10h_check_answerable.json" POST "$B2/api/question-entity-coverage" --json '{"question":"Which functions call upsert_table_term?"}'
  "$PY" "$HERE/ask_questions.py" "$B2" "$EVALUATION_FILE" "$RESP/10i_ask_with_key" ${AO_QIDS:-1 5 11 15 22}
  stop_started
fi

say "replace local paths in captured evidence with placeholders"
for f in $(grep -rlF -e "$CLONE" -e "$REPO" -e "$HOME" "$RESP" "$LOGS" "$CERT" 2>/dev/null); do
  sed -i.bak -e "s#$CLONE#<auto-ontology>#g" -e "s#$REPO#<code-ontology-bridge>#g" -e "s#$HOME#~#g" "$f" && rm -f "$f.bak"
done

say "secret scan of everything written (counts only)"
grep -rcE "nvapi-[A-Za-z0-9_-]{20}|sk-or-v1-[A-Za-z0-9]{20}" "$RESP" "$LOGS" "$CERT" 2>/dev/null | awk -F: '$2>0' > "$RESP/99_secret_scan.txt" || true
[ -s "$RESP/99_secret_scan.txt" ] && { echo "API key string found in outputs; see responses/99_secret_scan.txt"; exit 3; }
echo "secret scan: 0 files in responses/, logs/ or cert/ contain the NVIDIA key prefix" > "$RESP/99_secret_scan.txt"
say "done; evidence in $RESP"
