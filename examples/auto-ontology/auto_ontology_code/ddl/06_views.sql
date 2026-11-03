-- Views for schema code: code map of https://github.com/NVIDIA/auto-ontology
-- commit cdaf61e1bd0cf3820d11d72b43bb460816aebbd3  source_fingerprint 158fe223627725d6  snapshot cdaf61e1bd0c-158fe2236277
-- built by code-ontology-bridge 0.1.0 at 2026-11-03T08:41:39Z; known limits in table code.snapshot

-- Every symbol with the number of resolved direct call sites that target it, the number of callback references to it, and the number of distinct callers of either kind.
CREATE OR REPLACE VIEW code.inbound_call_counts AS
SELECT s.symbol_id, s.file_id, s.name, s.qualname, s.kind, s.is_public,
       SUM(CASE WHEN c.call_kind = 'direct' THEN 1 ELSE 0 END) AS inbound_calls,
       SUM(CASE WHEN c.call_kind = 'callback' THEN 1 ELSE 0 END) AS callback_references,
       COUNT(DISTINCT c.caller_symbol_id) AS distinct_callers
FROM code.symbols s
LEFT JOIN code.calls c ON c.callee_symbol_id = s.symbol_id
GROUP BY s.symbol_id, s.file_id, s.name, s.qualname, s.kind, s.is_public;

-- Public symbols in non-test files whose file no test file links to.
CREATE OR REPLACE VIEW code.untested_public_symbols AS
SELECT s.symbol_id, s.file_id, s.name, s.qualname, s.kind
FROM code.symbols s
JOIN code.files f ON f.file_id = s.file_id
WHERE s.is_public
  AND NOT f.is_test
  AND NOT EXISTS (SELECT 1 FROM code.test_links t WHERE t.target_file_id = s.file_id);
