"""Parse a questions CSV into QuestionItem objects."""
import csv
import io

from app.experiments.schemas import QUESTION_TYPES, QuestionItem


def _split(cell: str | None) -> list[str]:
    """The non-empty '|'-separated items of a cell."""
    return [p.strip() for p in (cell or "").split("|") if p.strip()]


def _hops(cell: str | None, evidence: list[str], line: int) -> list[int] | None:
    """Hop of each evidence passage; all in hop 1 when the column is empty."""
    items = _split(cell)
    if not items:
        return [1] * len(evidence) if evidence else None
    if len(items) != len(evidence) or not all(i.isdigit() and int(i) >= 1 for i in items):
        raise ValueError(
            f"line {line}: evidencia_salto needs one hop number (1, 2, ...) for each of "
            f"the {len(evidence)} evidencia_referencia passages"
        )
    return [int(i) for i in items]


def parse_questions_csv(content: str) -> list[QuestionItem]:
    """Parse a CSV with 'pergunta' and optional 'resposta_referencia',
    'evidencia_referencia' (passages separated by '|'), 'tipo', 'evidencia_salto'
    (the hop of each passage) and 'entidades_ponte' columns."""
    reader = csv.DictReader(io.StringIO(content))
    if "pergunta" not in (reader.fieldnames or []):
        raise ValueError("CSV missing required column: pergunta")
    items = []
    for line, row in enumerate(reader, start=2):
        text = (row.get("pergunta") or "").strip()
        if not text:
            continue
        reference = (row.get("resposta_referencia") or "").strip() or None
        evidence = _split(row.get("evidencia_referencia"))
        question_type = (row.get("tipo") or "").strip() or "simples"
        if question_type not in QUESTION_TYPES:
            raise ValueError(
                f"line {line}: unknown tipo '{question_type}' "
                f"(use {', '.join(QUESTION_TYPES)})"
            )
        items.append(
            QuestionItem(
                text=text,
                reference=reference,
                evidence=evidence or None,
                question_type=question_type,
                evidence_hops=_hops(row.get("evidencia_salto"), evidence, line),
                bridge_entities=_split(row.get("entidades_ponte")),
            )
        )
    return items
