"""Extract a chunk's entities and relations with an LLM, tolerating malformed lines.

The LLM answers one record per line, fields separated by '<|>':
    entidade<|>name<|>type<|>description
    relacao<|>source<|>target<|>keywords<|>description
Small local models drift from the format, so each line is parsed on its own: a
malformed line is dropped and counted, never failing the whole chunk.
"""
import re
import unicodedata

from pydantic import BaseModel

from app.core.llm.base import LLM
from app.core.prompts import load_prompt

FIELD_SEP = "<|>"
END_MARKER = "<|FIM|>"
# List markers and numbering models put before a record.
_LIST_MARKER = re.compile(r"^(?:\d+[.)]|[-*•>])\s*")
_QUOTES = "`'\" "
_HEADING = re.compile(r"^#{1,6}\s+\S")


class Entity(BaseModel):
    """An entity a chunk mentions."""

    name: str
    type: str
    description: str


class Relation(BaseModel):
    """A relation a chunk states between two of its entities."""

    source: str
    target: str
    keywords: str
    description: str


class Extraction(BaseModel):
    """What one chunk yielded, and how many of the LLM's lines could not be read."""

    entities: list[Entity] = []
    relations: list[Relation] = []
    failed_lines: int = 0


def _fields(line: str) -> list[str]:
    """The record's fields, without list markers, wrapping parentheses or quotes."""
    line = _LIST_MARKER.sub("", line)
    if line.startswith("(") and line.endswith(")"):
        line = line[1:-1]
    return [f.strip(_QUOTES) for f in line.split(FIELD_SEP)]


def _entity_type(raw: str) -> str:
    """Entity type as the prompt spells it: lowercase, no accents.

    "Organização" -> "organizacao".
    """
    folded = unicodedata.normalize("NFKD", raw.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def parse_extraction(reply: str) -> Extraction:
    """Read the LLM's reply line by line; malformed lines are dropped and counted."""
    result = Extraction()
    for raw in reply.splitlines():
        line = raw.strip()
        if not line or line == END_MARKER:
            continue
        fields = _fields(line)
        tag = fields[0].lower()
        if tag == "entidade" and len(fields) == 4 and all(fields[1:3]):
            result.entities.append(
                Entity(name=fields[1], type=_entity_type(fields[2]), description=fields[3])
            )
        elif tag == "relacao" and len(fields) == 5 and all(fields[1:3]):
            result.relations.append(
                Relation(source=fields[1], target=fields[2], keywords=fields[3],
                         description=fields[4])
            )
        else:
            result.failed_lines += 1
    return result


def without_headings(chunk: str) -> str:
    """The chunk without the Markdown heading lines it starts with.

    The markdown chunker prefixes each chunk with its heading path ("# Guia de
    ...", "## Perguntas frequentes ..."): the extractor took those titles for
    entities, and the guide's title became an entity in 94 chunks (experiment #21).
    The section's body names its subject again, so nothing is lost.
    """
    lines = chunk.splitlines()
    start = 0
    while start < len(lines) and (_HEADING.match(lines[start]) or not lines[start].strip()):
        start += 1
    return "\n".join(lines[start:]).strip()


def extract(llm: LLM, text: str, prompt: str | None = None) -> Extraction:
    """Ask the LLM for the chunk's entities and relations and parse its reply."""
    template = prompt or load_prompt("graph", "extract")
    return parse_extraction(llm.generate(template.format(text=text)))
