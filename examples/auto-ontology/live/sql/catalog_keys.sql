-- Tables, columns, primary keys and declared foreign keys in the catalog.
SELECT (SELECT count(*) FROM catalog_table) AS tables,
       (SELECT count(*) FROM catalog_column) AS columns,
       (SELECT count(*) FROM catalog_table WHERE cardinality(pk) > 0) AS tables_with_pk,
       (SELECT count(*) FROM column__foreign_key) AS foreign_keys,
       (SELECT string_agg(name, ',' ORDER BY name) FROM catalog_table) AS table_names;
