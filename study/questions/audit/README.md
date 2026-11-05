# Reference audit, 5 November 2026

After the model runs, an outside review found that the reference SQL for `ao-03` does not apply the question's own restriction to functions and methods, and supplied an executable counterexample (`ao03_reference_counterexample.py`, with its output). Four further auditors, one per repository, then checked all 48 references against their questions' wording. They saw the questions, the databases and the generator, and not the model responses or scores. Their findings are the four JSON files here.

The decisions taken from these findings, before any rescoring, are in [`../corrections.json`](../corrections.json):

- a reference that omits a restriction the question states is corrected;
- where the wording supports two readings, either reading is accepted, applied consistently on all nine databases;
- the counterfactual databases are regenerated after fixing one generator defect (new files under a nested `tests/` folder were marked as non-test).

`python study/check_references.py` confirms every reading runs on all nine databases and that no corrected reference changes its answer on the real database.
