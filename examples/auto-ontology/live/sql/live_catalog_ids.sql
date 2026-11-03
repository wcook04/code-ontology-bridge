-- Live catalog ids by name, as one JSON object for remap_catalog_ids.py.
SELECT json_build_object(
  'database', (SELECT json_object_agg(d.name, d.id) FROM catalog_database d),
  'schema',   (SELECT json_object_agg(d.name || '.' || s.name, s.id) FROM catalog_schema s JOIN catalog_database d ON d.id = s.database_id),
  'table',    (SELECT json_object_agg(s.name || '.' || t.name, t.id) FROM catalog_table t JOIN catalog_schema s ON s.id = t.schema_id),
  'column',   (SELECT json_object_agg(s.name || '.' || t.name || '.' || c.name, c.id) FROM catalog_column c JOIN catalog_table t ON t.id = c.table_id JOIN catalog_schema s ON s.id = t.schema_id)
);
