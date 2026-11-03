"""Governance sidecars for an Auto Ontology model of a codebase.

Three components, each plugging into an entry point Auto Ontology already has:

- ``certification``: append-only certification events, pluggable checks,
  freshness against source fingerprints, and a planner for Auto Ontology's
  existing PATCH routes.
- ``evidence``: wraps the MCP ``DataAnswer`` with the tables, columns and terms
  its SQL touched and their certification state.
- ``reconcile``: resolves several definitions of one term in a fixed order and
  reports ambiguity instead of renaming.
"""
