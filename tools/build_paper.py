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


def main() -> None:
    source = (ROOT / 'docs/case-study.md').read_text()
    # Metadata supplies the PDF title; retain the heading for GitHub readers.
    source = re.sub(r'^# Querying a Codebase with NVIDIA Auto Ontology\n', '', source, count=1, flags=re.M)

    def public_link(match: re.Match) -> str:
        target = match[1]
        if urlsplit(target).scheme or target.startswith('#'):
            return match[0]
        path = posixpath.normpath('docs/' + target)
        return '](https://github.com/wcook04/code-ontology-bridge/blob/main/' + path + ')'

    source = re.sub(r'\]\(([^)]+)\)', public_link, source)
    with tempfile.TemporaryDirectory(prefix='cob-paper-') as tmp:
        folder = Path(tmp)
        md = folder / 'paper.md'
        header = folder / 'header.tex'
        md.write_text(source)
        header.write_text(r'''\usepackage{microtype}
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
