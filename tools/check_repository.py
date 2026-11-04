#!/usr/bin/env python3
"""Check repository roles and local Markdown routes, in the worktree or index."""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT_FILES = {
    '.gitignore', '.gitattributes', '.python-version', 'README.md', 'CONTRIBUTING.md', 'GAPS.md',
    'SPEC.md', 'LICENSE', 'pyproject.toml', 'uv.lock',
}
REQUIRED = {
    'README.md', 'CONTRIBUTING.md', 'GAPS.md', 'SPEC.md', 'LICENSE', 'pyproject.toml',
    'docs/README.md', 'docs/case-study.md', 'docs/case-study.pdf',
    'docs/reproduction.md', 'docs/governance.md',
    'code_ontology_bridge/cli.py', 'tools/check_repository.py',
    'tools/build_paper.sh', 'tools/build_paper.py', '.github/workflows/checks.yml',
    'examples/auto-ontology/live/RESULTS.md',
}


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(root), *args])


def candidates(root: Path, index: bool) -> set[str]:
    args = ['ls-files', '-z', '--cached']
    if not index:
        args += ['--others', '--exclude-standard']
    names = {x.decode('utf-8') for x in git(root, *args).split(b'\0') if x}
    return names if index else {x for x in names if (root / x).is_file()}


def allowed(name: str) -> bool:
    p = PurePosixPath(name)
    if len(p.parts) == 1:
        return name in ROOT_FILES
    owner = p.parts[0]
    if owner == 'docs':
        return p.suffix in {'.md', '.pdf'}
    if owner == 'tools':
        return len(p.parts) == 2 and p.suffix in {'.py', '.sh'}
    if owner == 'tests':
        return p.suffix == '.py'
    if owner == '.github':
        return p.parts[1] == 'workflows' and p.suffix in {'.yml', '.yaml'}
    if owner == 'eval':
        return name in {'eval/auto_ontology_questions.json', 'eval/custom_analyses.json', 'eval/answer_contracts.json'}
    if owner == 'code_ontology_bridge':
        return p.suffix == '.py' or (p.suffix == '.json' and
            p.parts[1:3] == ('governance', 'examples'))
    if p.parts[:2] == ('examples', 'auto-ontology'):
        # Historical captures and replay programs have stable published paths.
        if len(p.parts) == 3:
            return p.name in {'.gitignore', 'summary.json', 'reproduce.sh',
                              'auto_ontology_code.model.yaml'}
        if p.parts[2] == 'auto_ontology_code':
            return p.suffix in {'.csv', '.sql', '.json'}
        if p.parts[2] == 'live':
            return p.suffix in {'.md', '.py', '.sh', '.json', '.yaml', '.txt', '.log', '.sql', '.patch'} or p.name in {'.gitignore', 'ingestion_keyed.compile_marker'}
    return False


def anchors(text: str) -> set[str]:
    result = set(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    counts: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if match:
            slug = re.sub(r'[^\w\- ]', '', match[1].lower()).replace(' ', '-')
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            result.add(slug if not n else f'{slug}-{n}')
    return result


def check(root: Path, index: bool = False) -> list[str]:
    names = candidates(root, index)
    problems = [f'missing required route: {x}' for x in sorted(REQUIRED - names)]
    problems += [f'file has no directory role: {x}' for x in sorted(names) if not allowed(x)]
    cache: dict[str, str] = {}

    def read(name: str) -> str:
        if name not in cache:
            data = git(root, 'show', ':' + name) if index else (root / name).read_bytes()
            cache[name] = data.decode('utf-8')
        return cache[name]

    for name in sorted(n for n in names if n.endswith('.md')):
        source = re.sub(r'```.*?```', '', read(name), flags=re.S)
        for match in re.finditer(r'!?\[[^\]\n]*\]\(([^)\n]+)\)', source):
            url = match[1].strip().strip('<>')
            parts = urlsplit(url)
            if parts.scheme or parts.netloc:
                continue
            path = unquote(parts.path)
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
            exists = target in names or any(n.startswith(target.rstrip('/') + '/') for n in names)
            if not exists:
                problems.append(f'{name}: broken link {url}')
            elif parts.fragment and target in names and target.endswith('.md'):
                if unquote(parts.fragment) not in anchors(read(target)):
                    problems.append(f'{name}: missing heading {url}')
    if 'README.md' in names:
        for route in ('docs/case-study.md', 'docs/reproduction.md', 'docs/README.md',
                      'examples/auto-ontology/live/RESULTS.md', 'CONTRIBUTING.md'):
            if f']({route})' not in read('README.md'):
                problems.append(f'README.md: missing reader route {route}')
    if 'pyproject.toml' in names:
        import tomllib
        if tomllib.loads(read('pyproject.toml'))['project'].get('readme') != 'README.md':
            problems.append('pyproject.toml: package description must use README.md')
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', action='store_true', help='read staged paths and contents')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        problems = check(args.root, args.index)
    except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError) as error:
        print(f'FAIL: cannot inspect repository: {error}')
        return 1
    for problem in problems:
        print('FAIL:', problem)
    if not problems:
        print('PASS: directory roles, required reader routes and local Markdown links')
    return bool(problems)


if __name__ == '__main__':
    raise SystemExit(main())
