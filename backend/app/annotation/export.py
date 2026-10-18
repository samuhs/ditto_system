"""A Rodada de anotação as CSV (every note, long format) or LaTeX (booktabs) tables.

The LaTeX reads the same dicts the page draws (`round_agreement`, `round_validation`), so
what is published matches what is shown.
"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.annotation.rubric import DIMENSIONS
from app.annotation.service import translate_pair_preference
from app.core.db.models import (
    AnnotationItem,
    AnnotationNote,
    AnnotationPairItem,
    AnnotationPairNote,
    AnnotationRound,
    Annotator,
)

_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def _cell(text: str, for_excel: bool) -> str:
    """Free text as a cell; for spreadsheets, a leading = + - @ is quoted so it is never run as a formula."""
    text = text or ""
    return "'" + text if for_excel and text[:1] in ("=", "+", "-", "@") else text


def to_csv(session: Session, rnd: AnnotationRound, final: dict, for_excel: bool = False) -> str:
    """One row per note and Rubrica dimension, with the Item's Nota final, Combinação,
    question type and automatic metrics (long format, ready for R or pandas). `for_excel`
    separates columns with ";" (Excel in PT-BR) and quotes text that would run as a formula."""
    metrics = sorted({m for item in rnd.items for m in item.auto_scores})
    final_by_item = {entry["id"]: entry for entry in final["items"]}
    rows = session.execute(
        select(AnnotationNote, Annotator.name, AnnotationItem)
        .join(Annotator, AnnotationNote.annotator_id == Annotator.id)
        .join(AnnotationItem, AnnotationNote.item_id == AnnotationItem.id)
        .where(AnnotationItem.round_id == rnd.id)
        .order_by(AnnotationItem.position, Annotator.name)
    ).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";" if for_excel else ",")
    writer.writerow([
        "rodada", "item", "posicao", "pergunta", "tipo_pergunta", "chunking", "embedding", "rag",
        "retriever", "llm", "avaliador", "dimensao", "nota", "nao_consegue_avaliar", "motivo",
        "comentario", "nota_final", "situacao_final", *metrics,
    ])
    for note, name, item in rows:
        combo = item.combination
        entry = final_by_item.get(item.id, {})
        for dim in DIMENSIONS:
            score = getattr(note, dim)
            writer.writerow([
                rnd.id, item.id, item.position, _cell(item.question, for_excel), item.question_type or "",
                combo.get("chunking", ""), combo.get("embedding", ""), combo.get("rag", ""),
                combo.get("retriever", ""), combo.get("llm", ""), _cell(name, for_excel), dim,
                "" if score is None else score, "sim" if note.cannot_evaluate else "não",
                _cell(note.reason, for_excel), _cell(note.comment, for_excel),
                "" if entry.get("final", {}).get(dim) is None else entry["final"][dim],
                entry.get("status", ""),
                *("" if item.auto_scores.get(m) is None else item.auto_scores[m] for m in metrics),
            ])
    return buffer.getvalue()


def to_pair_csv(session: Session, rnd: AnnotationRound, final: dict, for_excel: bool = False) -> str:
    """One row per note of a pairwise Rodada (long format), with the unblinded mapping (which
    Combinação was A for that Item) and the preference translated to which Combinação it
    favors."""
    final_by_item = {entry["id"]: entry for entry in final["items"]}
    rows = session.execute(
        select(AnnotationPairNote, Annotator.name, AnnotationPairItem)
        .join(Annotator, AnnotationPairNote.annotator_id == Annotator.id)
        .join(AnnotationPairItem, AnnotationPairNote.item_id == AnnotationPairItem.id)
        .where(AnnotationPairItem.round_id == rnd.id)
        .order_by(AnnotationPairItem.position, Annotator.name)
    ).all()
    run1, run2 = rnd.pair_run_1 or {}, rnd.pair_run_2 or {}
    label1 = f"{run1.get('rag', '')}·{run1.get('llm', '')}"
    label2 = f"{run2.get('rag', '')}·{run2.get('llm', '')}"

    def result_text(item: AnnotationPairItem, preference: str | None) -> str:
        side = translate_pair_preference(item, preference)
        return {None: "", "tie": "empate", "1": f"{label1} melhor", "2": f"{label2} melhor"}[side]

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";" if for_excel else ",")
    writer.writerow([
        "rodada", "item", "posicao", "pergunta", "tipo_pergunta",
        "run1_chunking", "run1_embedding", "run1_rag", "run1_retriever", "run1_llm",
        "run2_chunking", "run2_embedding", "run2_rag", "run2_retriever", "run2_llm",
        "a_e_do_run", "avaliador", "preferencia_bruta", "preferencia", "motivos",
        "nao_consegue_avaliar", "motivo", "comentario", "preferencia_final", "situacao_final",
    ])
    for note, name, item in rows:
        entry = final_by_item.get(item.id, {})
        writer.writerow([
            rnd.id, item.id, item.position, _cell(item.question, for_excel), item.question_type or "",
            run1.get("chunking", ""), run1.get("embedding", ""), run1.get("rag", ""),
            run1.get("retriever", ""), run1.get("llm", ""),
            run2.get("chunking", ""), run2.get("embedding", ""), run2.get("rag", ""),
            run2.get("retriever", ""), run2.get("llm", ""),
            "1" if item.a_is_1 else "2", _cell(name, for_excel),
            note.preference or "", result_text(item, note.preference),
            ";".join(note.reasons or []), "sim" if note.cannot_evaluate else "não",
            _cell(note.reason, for_excel), _cell(note.comment, for_excel),
            result_text(item, entry.get("preference")), entry.get("status", ""),
        ])
    return buffer.getvalue()


def _tex(text: str) -> str:
    return "".join(_LATEX_SPECIALS.get(ch, ch) for ch in str(text))


def _table(caption: str, columns: str, header: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "\\begin{table}[ht]", "\\centering", "\\small", f"\\caption{{{caption}}}",
        f"\\begin{{tabular}}{{{columns}}}", "\\toprule", " & ".join(header) + " \\\\", "\\midrule",
        *(" & ".join(row) + " \\\\" for row in rows),
        "\\bottomrule", "\\end{tabular}", "\\end{table}", "",
    ]


_TEXTS = {
    "pt": {
        "dims": {"correctness": "Correção", "grounding": "Fundamentação"},
        "agreement": "Concordância entre avaliadores ({who}) na rodada {name}: $\\alpha$ de Krippendorff "
                     "ordinal e, com dois avaliadores, $\\kappa$ ponderado (pesos quadráticos); IC 95\\% por "
                     "bootstrap ({resamples} reamostragens, semente 0).",
        "agreement_header": ["Dimensão", "n", "$\\alpha$ ordinal [IC 95\\%]", "$\\kappa$ ponderado [IC 95\\%]"],
        "spearman": "Correlação de Spearman entre a Nota final humana e as métricas automáticas na rodada {name}; "
                    "IC 95\\% por bootstrap. {pending} respostas com dimensão pendente de adjudicação ficaram "
                    "fora dessa dimensão.",
        "spearman_header": ["Nota humana", "Métrica", "n", "$\\rho$ [IC 95\\%]"],
        "means": "Correção humana (0--2) e \\texttt{{answer\\_correctness}} médias por Combinação, "
                 "sobre as mesmas respostas, na rodada {name}; IC 95\\% por bootstrap.",
        "means_header": ["Técnica $\\cdot$ LLM", "n", "Correção humana", "\\texttt{answer\\_correctness}"],
    },
    "en": {
        "dims": {"correctness": "Correctness", "grounding": "Grounding"},
        "agreement": "Inter-annotator agreement ({who}) on round {name}: ordinal Krippendorff's $\\alpha$ "
                     "and, with two annotators, weighted $\\kappa$ (quadratic weights); 95\\% bootstrap CI "
                     "({resamples} resamples, seed 0).",
        "agreement_header": ["Dimension", "n", "ordinal $\\alpha$ [95\\% CI]", "weighted $\\kappa$ [95\\% CI]"],
        "spearman": "Spearman correlation between the final human score and the automatic metrics on round "
                    "{name}; 95\\% bootstrap CI. {pending} answers with a dimension pending adjudication were "
                    "left out of that dimension.",
        "spearman_header": ["Human score", "Metric", "n", "$\\rho$ [95\\% CI]"],
        "means": "Mean human correctness (0--2) and mean \\texttt{{answer\\_correctness}} per combination, "
                 "over the same answers, on round {name}; 95\\% bootstrap CI.",
        "means_header": ["Technique $\\cdot$ LLM", "n", "Human correctness", "\\texttt{answer\\_correctness}"],
    },
}


def to_latex(agreement: dict, validation: dict, decimal: str = "point", resamples: int = 10_000,
             lang: str = "pt") -> str:
    """Booktabs tables of the Concordância and of the Spearman correlations with the metrics, with
    captions in Portuguese (`lang="pt"`) or English (`lang="en"`, always with decimal points, for the
    English version of the paper). `decimal="comma"` writes 0,812 instead of 0.812 in Portuguese."""
    texts = _TEXTS[lang]
    comma = decimal == "comma" and lang == "pt"
    sep = "," if comma else "."
    list_sep = ";" if comma else ","

    def num(value: float | None) -> str:
        return "--" if value is None else f"{value:.3f}".replace(".", sep)

    def with_ci(value, low, high) -> str:
        if value is None:
            return "--"
        if low is None or high is None:
            return num(value)
        return f"{num(value)}~[{num(low)}{list_sep} {num(high)}]"

    name = _tex(agreement["round"]["name"])
    who = ", ".join(_tex(n) for n in agreement["avaliadores"]) or "--"
    count = f"{resamples:,}".replace(",", "." if comma else ",")
    dims = texts["dims"]
    lines = ["% Requires \\usepackage{booktabs}. Generated by the Ditto Anotação humana."]
    lines += _table(
        texts["agreement"].format(who=who, name=name, resamples=count), "lrll", texts["agreement_header"],
        [[dims[dim], str(d["n"]), with_ci(d["alpha"]["value"], d["alpha"]["low"], d["alpha"]["high"]),
          with_ci(*(d["kappa"][k] for k in ("value", "low", "high"))) if d["kappa"] else "--"]
         for dim, d in agreement["dimensions"].items()],
    )
    correlations = [(dim, c) for dim in ("correctness", "grounding") for c in validation["correlations"][dim]]
    lines += _table(
        texts["spearman"].format(name=name, pending=validation["pending"]), "llrl", texts["spearman_header"],
        [[dims[dim], f"\\texttt{{{_tex(c['metric'])}}}", str(c["n"]), with_ci(c["rho"], c["low"], c["high"])]
         for dim, c in correlations],
    )
    if validation["by_combination"]:
        lines += _table(
            texts["means"].format(name=name), "lrll", texts["means_header"],
            [[f"{_tex(g['rag'])} $\\cdot$ {_tex(g['llm'])}", str(g["n"]),
              with_ci(g["human"]["mean"], g["human"]["low"], g["human"]["high"]),
              with_ci(g["automatic"]["mean"], g["automatic"]["low"], g["automatic"]["high"])]
             for g in validation["by_combination"]],
        )
    return "\n".join(lines)
