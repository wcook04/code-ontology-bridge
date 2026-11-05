# Adjudication: author versus independent annotator

Each repository's 12 questions were answered twice, by the author (reference SQL) and by an annotator who saw only the question text and output columns. `agree` compares the two results; `flags` counts readings the annotator thought plausible. Every flagged or disagreeing question was reworded so one reading remains, or removed. Questions not listed here were unchanged. The original drafts and annotations are kept in `study/questions/authoring/`.

## httpx — 12 of 12 agree before any change

- **httpx-03** (flag: do helper files under `tests/`, such as `tests/common.py`, count as source files? 18 vs 20 rows). Reworded to say that every file under `tests/`, helpers and `conftest.py` included, is a test file. Reference unchanged.
- **httpx-12** (flag: does `functools.partial(trace, ...)` hand `trace` over? 4 vs 3 rows). Reworded to say that a function given to `functools.partial` counts. Reference unchanged.

## rich — 12 of 12 agree before any change

- **rich-03** (flag: do calls through a local alias `_cell_len = cell_len` count? 16 vs 18). Reworded: only calls naming `cell_len` itself count. The database cannot link aliased calls; this is an extractor limit recorded in the source checks.
- **rich-05** (flag: does `from . import box` also import `rich/__init__.py`? 16 vs 17). Reworded to say it imports `rich/box.py` only.
- **rich-06** (flags: does `rich/text.py` qualify; do package imports count? 22 vs 21). Reworded to state both.
- **rich-11** (flag: are `@overload` stubs and repeated definitions counted once or each? changes the fifth file). Reworded: every definition counts.
- rich-04 and rich-07 flags changed no answer; rich-07 already states its counting rule. Unchanged.

## click — 12 of 12 agree before any change

- **click-02** (flag: is a leading `#` comment block a docstring? 3 vs 4). Reworded: it is not.
- **click-03** (flag: do imports under `TYPE_CHECKING` count? 6 vs 5). Reworded: they do.
- **click-06** (flag: is `tests/conftest.py` a test file? 4 vs 3). Reworded: it is.
- **click-09** (flag: does `Group.__init__` override `Command.__init__`? 7 vs 6). Reworded: it does.
- **click-05** flags concerned the nested-helper rule, which the question already states in full, and the identity of `prompt`, which the question does not name. Unchanged.
- Remaining flags changed no answer. Unchanged.

## auto_ontology — 12 of 12 agree before any change

- **ao-02** (flag: do routers passed only inside an if/else branch count? 9 vs 6). Reworded: they count.
- **ao-03** (flag: should `PiiDetector.detect` count, since `self._backend.classify` is at run time a direct caller? 13 vs 14). Reworded: only calls to a named function or a method on `self` are followed. The extractor records the other call as a dynamic attribute; recorded as a source-fidelity limit.
- **ao-04** (flag: does a test that calls `create_graph()`, which constructs agents, count? 8 vs 1). Reworded: it does not.
- **ao-05** (flag: do files in `dev_tools/`, outside the `auto_ontology` package, count? 23 vs 21). Reworded: they do.
- **ao-06** (flag: is a leading `#` comment a docstring? 7 vs 6). Reworded: it is not.
- **ao-08** (flag: keep ties at fifth place? 5 vs 7). Reworded: exactly five rows.
- **ao-09** (flag: one row per link reason? 3 vs 4). Reworded: each file once.
- ao-01, ao-07, ao-10, ao-12 flags changed no answer. Unchanged.

## Totals

48 questions, 48 author–annotator agreements before rewording. 17 questions reworded to remove a reading the annotator flagged; no reference SQL changed and no question was removed.
