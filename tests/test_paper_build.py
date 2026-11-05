"""PDF links must survive temporary build paths and branch cleanup."""
import importlib.util
from pathlib import Path

BUILDER = Path(__file__).resolve().parents[1] / 'tools/build_paper.py'
spec = importlib.util.spec_from_file_location('paper_build', BUILDER)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_local_figures_and_durable_public_links():
    source = ('![A diagram](figures/architecture.png)\n'
              '[Spec](../SPEC.md#entry-points)\n'
              '[External](https://example.com/source)\n'
              '[Section](#abstract)\n')
    result = builder.prepare_source(source)
    assert f'![A diagram]({builder.ROOT}/docs/figures/architecture.png)' in result
    assert '[Spec](https://github.com/wcook04/code-ontology-bridge/blob/main/SPEC.md#entry-points)' in result
    assert '[External](https://example.com/source)' in result
    assert '[Section](#abstract)' in result
    assert 'codex/clarify-repository' not in result
