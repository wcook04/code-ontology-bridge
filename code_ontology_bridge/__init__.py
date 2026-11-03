"""Give NVIDIA Auto Ontology an ontology of a codebase through the entry points it already has.

The code map (``codemap``) reads a Python repository with the standard library
``ast`` module and produces relational rows in schema ``code``. The exporters
(``export``) write those rows as a DuckDB file, an ontology-sql-eval dataset
folder and an Auto Ontology model-import YAML document.
"""

__version__ = "0.1.0"
BUILDER_NAME = "code-ontology-bridge"
