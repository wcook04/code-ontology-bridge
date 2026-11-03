"""Read fixed headings, contract atoms and descriptions out of docstrings, verbatim.

The heading grammar: a line that is an upper-case word in square brackets
(``[PURPOSE]``) opens a section that runs to the next such line; inside a
section, lines of the form ``- Atom: value`` carry contract atoms, and indented
continuation lines extend the previous atom. Nothing here paraphrases: every
returned string is docstring text with whitespace collapsed.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass

FIXED_HEADINGS = ("PURPOSE", "INTERFACE", "FLOW", "DEPENDENCIES", "CONSTRAINTS")
ATOMS = ("Teleology", "Mechanism", "Guarantee", "Fails", "Reads", "Writes")

_TAG_LINE = re.compile(r"^\s*\[(?P<tag>[A-Z][A-Z_]*)\]\s*(?P<rest>.*)$")
_ATOM_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?P<atom>[A-Za-z][A-Za-z0-9-]*):\s*(?P<value>.*)$")
# Several atoms on one line ("- Teleology: x - Mechanism: y") are separated first.
_SIBLING_ATOM = re.compile(r"\s+-\s+(?=(?:" + "|".join(ATOMS) + r"):)")


def _collapse(text: str) -> str:
    return " ".join(text.split())


def clean(docstring: str | None) -> str:
    return inspect.cleandoc(docstring) if docstring else ""


def split_tags(docstring: str | None) -> dict[str, str]:
    """Return ``{TAG: body}`` for every bracketed tag, bodies kept multi-line."""
    text = clean(docstring)
    blocks: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = _TAG_LINE.match(line)
        if match:
            if current is not None:
                blocks.setdefault(current, "\n".join(body).strip())
            current = match.group("tag")
            body = [match.group("rest")] if match.group("rest").strip() else []
        elif current is not None:
            body.append(line)
    if current is not None:
        blocks.setdefault(current, "\n".join(body).strip())
    return blocks


def extract_atoms(body: str) -> list[tuple[str, str]]:
    """Ordered ``(atom, value)`` pairs found in one tag body; unknown atoms are ignored."""
    found: list[tuple[str, str]] = []
    current: int | None = None
    for raw in body.splitlines():
        for line in _SIBLING_ATOM.split(raw) if raw.strip() else [raw]:
            stripped = line.strip()
            if not stripped:
                current = None
                continue
            match = _ATOM_LINE.match(line)
            if match:
                atom = match.group("atom")
                if atom in ATOMS:
                    found.append((atom, _collapse(match.group("value"))))
                    current = len(found) - 1
                else:
                    current = None
                continue
            if current is not None and not stripped.startswith(("-", "*")):
                atom, value = found[current]
                found[current] = (atom, _collapse(f"{value} {stripped}"))
            else:
                current = None
    return found


@dataclass(frozen=True)
class Heading:
    heading: str
    value: str


def headings(docstring: str | None) -> list[Heading]:
    """Fixed headings (as ``[TAG]``) followed by the atoms inside each, in document order."""
    out: list[Heading] = []
    for tag, body in split_tags(docstring).items():
        if tag not in FIXED_HEADINGS:
            continue
        out.append(Heading(f"[{tag}]", body))
        for atom, value in extract_atoms(body):
            out.append(Heading(atom, value))
    return out


def first_paragraph(docstring: str | None) -> str:
    text = clean(docstring)
    if not text:
        return ""
    paragraph: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if paragraph:
                break
            continue
        if _TAG_LINE.match(line):
            break
        paragraph.append(line)
    return _collapse(" ".join(paragraph))


def module_description(docstring: str | None) -> tuple[str, str]:
    """``(description, source)`` with precedence [PURPOSE] heading, first paragraph, none.

    Under ``[PURPOSE]`` the Teleology atom is used when present, otherwise the
    whole section body.
    """
    tags = split_tags(docstring)
    purpose = tags.get("PURPOSE")
    if purpose:
        teleology = next((v for a, v in extract_atoms(purpose) if a == "Teleology" and v), None)
        return (teleology or _collapse(purpose)), "heading_purpose"
    paragraph = first_paragraph(docstring)
    if paragraph:
        return paragraph, "module_docstring"
    return "", "none"


def symbol_summary(docstring: str | None) -> tuple[str, str]:
    """``(summary, source)``: the Teleology atom of any tag, else the first paragraph."""
    for body in split_tags(docstring).values():
        teleology = next((v for a, v in extract_atoms(body) if a == "Teleology" and v), None)
        if teleology:
            return teleology, "docstring"
    paragraph = first_paragraph(docstring)
    return (paragraph, "docstring") if paragraph else ("", "none")
