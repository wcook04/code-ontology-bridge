#!/usr/bin/env python3
"""Build the paper from its maintained Markdown using Pandoc's article template.

Margins, article size, paragraph spacing and black links adapt the supplied
paper-return LaTeX draft. No separately maintained LaTeX body is required.
"""
from pathlib import Path
import posixpath
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = 'https://github.com/wcook04/code-ontology-bridge/blob/main/'


def prepare_source(source: str) -> str:
    """Resolve local images for Pandoc and give PDF links a durable public home."""
    source = re.sub(r'^# Querying a Codebase with NVIDIA Auto Ontology\n', '', source, count=1, flags=re.M)

    def resolve_link(match: re.Match) -> str:
        label, target = match.groups()
        if urlsplit(target).scheme or target.startswith('#'):
            return match[0]
        if label.startswith('!'):
            # The temporary Markdown lives outside docs; images must stay local.
            return f'{label}({(ROOT / "docs" / target).resolve().as_posix()})'
        path = posixpath.normpath('docs/' + target)
        return f'{label}({PUBLIC_ROOT}{path})'

    return re.sub(r'(!?\[[^\]\n]*\])\(([^)\n]+)\)', resolve_link, source)


def main() -> None:
    source = prepare_source((ROOT / 'docs/case-study.md').read_text())
    with tempfile.TemporaryDirectory(prefix='cob-paper-') as tmp:
        folder = Path(tmp)
        md = folder / 'paper.md'
        header = folder / 'header.tex'
        md.write_text(source)
        header.write_text(r'''\usepackage{microtype}
\usepackage{needspace}
\usepackage{etoolbox}
\usepackage{float}
\usepackage{caption}
\captionsetup{font=small}
\floatplacement{figure}{H}
\pretocmd{\subsubsection}{\Needspace{10\baselineskip}}{}{}
\BeforeBeginEnvironment{longtable}{\Needspace{8\baselineskip}}
\setlength{\parindent}{1em}
\setlength{\parskip}{0.15em}
\setlength{\emergencystretch}{3em}
''')
        subprocess.run([
            'pandoc', str(md), '--standalone', '--pdf-engine=tectonic',
            '-V', 'documentclass=article', '-V', 'fontsize=11pt', '-V', 'papersize=a4',
            '-V', 'geometry:margin=22mm', '-V', 'colorlinks=true',
            '-V', 'linkcolor=black', '-V', 'urlcolor=black',
            '--include-in-header', str(header), '-o', str(ROOT / 'docs/case-study.pdf'),
        ], check=True)
    print(ROOT / 'docs/case-study.pdf')


if __name__ == '__main__':
    main()
