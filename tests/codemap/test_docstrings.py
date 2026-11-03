from code_ontology_bridge.codemap import docstrings

FIXED = '''
[PURPOSE]
- Teleology: Build the code map.
  It spans two lines.
- Mechanism: Walk the tree. - Guarantee: Deterministic rows.

[INTERFACE]
- build() -> dict

[CONSTRAINTS]
- Fails: Never raises.
- Reads: The checkout.
- Writes: Nothing.
- Unknown: ignored.
'''


def test_fixed_headings_and_atoms_are_verbatim_and_ordered():
    heads = [(h.heading, h.value) for h in docstrings.headings(FIXED)]
    assert heads[0][0] == "[PURPOSE]"
    assert ("Teleology", "Build the code map. It spans two lines.") in heads
    assert ("Mechanism", "Walk the tree.") in heads
    assert ("Guarantee", "Deterministic rows.") in heads
    assert [h for h, _ in heads if h.startswith("[")] == ["[PURPOSE]", "[INTERFACE]", "[CONSTRAINTS]"]
    assert ("Fails", "Never raises.") in heads
    assert ("Writes", "Nothing.") in heads
    assert all(h != "Unknown" for h, _ in heads)


def test_description_precedence_purpose_first():
    assert docstrings.module_description(FIXED) == ("Build the code map. It spans two lines.", "heading_purpose")


def test_purpose_without_teleology_uses_whole_section():
    doc = "[PURPOSE]\nCompile things\nquickly.\n\n[FLOW]\n- a"
    assert docstrings.module_description(doc) == ("Compile things quickly.", "heading_purpose")


def test_description_falls_back_to_first_paragraph_then_none():
    doc = """Semantic layer compilation.

    Longer explanation that is not used.
    """
    assert docstrings.module_description(doc) == ("Semantic layer compilation.", "module_docstring")
    assert docstrings.module_description(None) == ("", "none")
    assert docstrings.module_description("   ") == ("", "none")


def test_symbol_summary_prefers_teleology():
    assert docstrings.symbol_summary("[ACTION]\n- Teleology: Do x.\n- Fails: None.") == ("Do x.", "docstring")
    assert docstrings.symbol_summary("Return the thing.\n\nMore.") == ("Return the thing.", "docstring")
    assert docstrings.symbol_summary(None) == ("", "none")
