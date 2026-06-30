"""Parse a questions CSV into QuestionItem objects."""
import csv
import io

from app.experiments.schemas import QuestionItem


def parse_questions_csv(content: str) -> list[QuestionItem]:
    """Parse a CSV with 'pergunta' and optional 'resposta_referencia' columns."""
    reader = csv.DictReader(io.StringIO(content))
    items = []
    for row in reader:
        text = (row.get("pergunta") or "").strip()
        if not text:
            continue
        reference = (row.get("resposta_referencia") or "").strip() or None
        items.append(QuestionItem(text=text, reference=reference))
    return items
