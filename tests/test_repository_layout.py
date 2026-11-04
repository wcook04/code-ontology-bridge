"""Exercise the repository gate against real Git worktree and index states."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

CHECKER = Path(__file__).resolve().parents[1] / 'tools/check_repository.py'
spec = importlib.util.spec_from_file_location('repository_check', CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def git(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, 'init')
    for name in checker.REQUIRED:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('')
    (tmp_path / 'README.md').write_text('\n'.join(f'[read]({name})' for name in (
        'docs/case-study.md', 'docs/reproduction.md', 'docs/README.md',
        'examples/auto-ontology/live/RESULTS.md', 'CONTRIBUTING.md')))
    (tmp_path / 'pyproject.toml').write_text('[project]\nreadme = "README.md"\n')
    (tmp_path / '.gitignore').write_text('/build/\n')
    git(tmp_path, 'add', '.')
    return tmp_path


def test_valid_tree_and_ignored_output(repository):
    (repository / 'build').mkdir()
    (repository / 'build/unowned.bin').write_bytes(b'output')
    assert checker.check(repository) == []
    assert checker.check(repository, True) == []


def test_misplaced_script_and_staged_addition(repository):
    (repository / 'maintenance.py').write_text('')
    assert any('no directory role' in p for p in checker.check(repository))
    git(repository, 'add', 'maintenance.py')
    assert any('no directory role' in p for p in checker.check(repository, True))


def test_staged_bad_link_survives_worktree_repair(repository):
    p = repository / 'docs/README.md'
    p.write_text('[missing](missing.md)')
    git(repository, 'add', 'docs/README.md')
    p.write_text('[valid](case-study.md)')
    assert checker.check(repository) == []
    assert any('broken link' in p for p in checker.check(repository, True))


def test_staged_removal_and_missing_anchor(repository):
    git(repository, 'rm', '-f', 'docs/case-study.md')
    assert any('missing required route' in p for p in checker.check(repository, True))
    (repository / 'docs/case-study.md').write_text('# Present\n')
    (repository / 'docs/README.md').write_text('[bad](case-study.md#absent)')
    assert any('missing heading' in p for p in checker.check(repository))


def test_historical_capture_exception(repository):
    p = repository / 'examples/auto-ontology/live/evidence/example/backend.log'
    p.parent.mkdir(parents=True)
    p.write_text('retained evidence')
    assert checker.check(repository) == []
