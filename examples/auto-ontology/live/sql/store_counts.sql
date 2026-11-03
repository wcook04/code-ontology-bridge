-- Row counts and imported_id coverage in Auto Ontology's Postgres store after import.
SELECT 'catalog_database' AS tbl, count(*) AS rows, count(imported_id) AS with_imported_id, count(*) FILTER (WHERE imported_id LIKE 'cob:%') AS cob_ids FROM catalog_database
UNION ALL SELECT 'catalog_schema', count(*), count(imported_id), count(*) FILTER (WHERE imported_id LIKE 'cob:%') FROM catalog_schema
UNION ALL SELECT 'catalog_table', count(*), count(imported_id), count(*) FILTER (WHERE imported_id LIKE 'cob:%') FROM catalog_table
UNION ALL SELECT 'catalog_column', count(*), count(imported_id), count(*) FILTER (WHERE imported_id LIKE 'cob:%') FROM catalog_column
UNION ALL SELECT 'term', count(*), count(imported_id), count(*) FILTER (WHERE imported_id LIKE 'cob:%') FROM term
UNION ALL SELECT 'column_attribute', count(*), count(imported_id), count(*) FILTER (WHERE imported_id LIKE 'cob:%') FROM column_attribute
UNION ALL SELECT 'custom_analysis', count(*), count(imported_id), count(*) FILTER (WHERE imported_id LIKE 'cob:%') FROM custom_analysis
UNION ALL SELECT 'column__semantic_fk', count(*), NULL, NULL FROM column__semantic_fk
UNION ALL SELECT 'column__foreign_key', count(*), NULL, NULL FROM column__foreign_key
UNION ALL SELECT 'column__has_attribute', count(*), NULL, NULL FROM column__has_attribute
UNION ALL SELECT 'table__term', count(*), NULL, NULL FROM table__term
ORDER BY 1;
