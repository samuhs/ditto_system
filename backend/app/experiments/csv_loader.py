"""Parse a questions CSV into QuestionItem objects."""
import csv
import io

from app.experiments.schemas import QuestionItem


def parse_questions_csv(content: str) -> list[QuestionItem]:
    """Parse a CSV with 'pergunta' and optional 'resposta_referencia' and
    'evidencia_referencia' columns (evidence passages separated by '|')."""
    reader = csv.DictReader(io.StringIO(content))
    if "pergunta" not in (reader.fieldnames or []):
        raise ValueError("CSV missing required column: pergunta")
    items = []
    for row in reader:
        text = (row.get("pergunta") or "").strip()
        if not text:
            continue
        reference = (row.get("resposta_referencia") or "").strip() or None
        passages = [p.strip() for p in (row.get("evidencia_referencia") or "").split("|")]
        evidence = [p for p in passages if p] or None
        items.append(QuestionItem(text=text, reference=reference, evidence=evidence))
    return items
