-- Certified flags, last modifier and modified time for the four certification targets.
SELECT 'term' AS kind, imported_id, name_certified, description_certified, NULL::boolean AS certified, modified_by, modified
FROM term WHERE imported_id IN ('cob:auto_ontology_code:term:symbols', 'cob:auto_ontology_code:term:calls')
UNION ALL
SELECT 'column_attribute', imported_id, NULL, NULL, certified, modified_by, modified
FROM column_attribute WHERE imported_id IN ('cob:auto_ontology_code:attribute:code.files.package', 'cob:auto_ontology_code:attribute:code.calls.resolution')
ORDER BY 1, 2;
