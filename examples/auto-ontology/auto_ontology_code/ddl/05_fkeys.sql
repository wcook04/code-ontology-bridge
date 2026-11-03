-- Foreign keys for schema code: code map of https://github.com/NVIDIA/auto-ontology
-- commit cdaf61e1bd0cf3820d11d72b43bb460816aebbd3  source_fingerprint 158fe223627725d6  snapshot cdaf61e1bd0c-158fe2236277
-- built by code-ontology-bridge 0.1.0 at 2026-11-03T08:41:39Z; known limits in table code.snapshot

ALTER TABLE code.headings ADD CONSTRAINT fk_headings_file_id FOREIGN KEY (file_id) REFERENCES code.files (file_id);
ALTER TABLE code.symbols ADD CONSTRAINT fk_symbols_file_id FOREIGN KEY (file_id) REFERENCES code.files (file_id);
ALTER TABLE code.class_bases ADD CONSTRAINT fk_class_bases_class_symbol_id FOREIGN KEY (class_symbol_id) REFERENCES code.symbols (symbol_id);
ALTER TABLE code.class_bases ADD CONSTRAINT fk_class_bases_base_symbol_id FOREIGN KEY (base_symbol_id) REFERENCES code.symbols (symbol_id);
ALTER TABLE code.calls ADD CONSTRAINT fk_calls_caller_symbol_id FOREIGN KEY (caller_symbol_id) REFERENCES code.symbols (symbol_id);
ALTER TABLE code.calls ADD CONSTRAINT fk_calls_callee_symbol_id FOREIGN KEY (callee_symbol_id) REFERENCES code.symbols (symbol_id);
ALTER TABLE code.imports ADD CONSTRAINT fk_imports_file_id FOREIGN KEY (file_id) REFERENCES code.files (file_id);
ALTER TABLE code.imports ADD CONSTRAINT fk_imports_imported_file_id FOREIGN KEY (imported_file_id) REFERENCES code.files (file_id);
ALTER TABLE code.test_links ADD CONSTRAINT fk_test_links_test_file_id FOREIGN KEY (test_file_id) REFERENCES code.files (file_id);
ALTER TABLE code.test_links ADD CONSTRAINT fk_test_links_target_file_id FOREIGN KEY (target_file_id) REFERENCES code.files (file_id);
