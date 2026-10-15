"""B3 (raw version): mechanical PDF -> Markdown conversion of the Maceió citizen-service base.

The raw version is the main level of B3 (campaign 2, section 3.3): text only, no '###'
headings added, so it tests H4 (markdown chunking without short headings). Only mechanical
cleanup, the same for every page:
- running headers/footers (a line that repeats on at least 30% of the pages) and the
  publisher's stamp (www.LeisMunicipais.com.br) are dropped; typographic ligature glyphs
  (fi, fl) become plain letters;
- a word hyphenated at the end of a line is joined;
- a line wrapped mid-sentence is joined to the previous one, unless it opens a new unit
  (article, paragraph sign, item numeral or letter, numbered step, an all-caps title);
- the IPLAM copy of the Lei Orgânica lost its 'ti'/'tí'/'fi'/'fí' ligatures (shown as
  U+FFFD); each broken word is repaired with the candidate found in a reference vocabulary
  (the 2007 DHnet copy, the service guide and the IPLAM copy's own intact words); the
  words no candidate resolves are listed in ligaduras_nao_resolvidas.txt.
Needs pdftotext (poppler). Stdlib only. Run from the repository root:

    python3 database/fontes_brutas/maceio_atendimento/gera_bruto.py
"""
import collections
import itertools
import re
import subprocess
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTES = HERE / "fontes"
OUT = HERE.parents[1] / "maceio_atendimento"
LIGATURES = ["ti", "tí", "fi", "fí", "ft", "tt", "fl", "ff"]
TITLE = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 /,()–-]{6,}$")
NEW_UNIT = re.compile(
    r"^(Art\.?\s*\d|ART\.?\s*\d|§|Parágrafo|PARÁGRAFO|[IVXLC]+\s*[-–.]\s|[a-z]\)\s|\d+\s*[.)-]\s|"
    r"TÍTULO|CAPÍTULO|SEÇÃO|SUBSEÇÃO|[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 /,()–-]{6,}$)")


def pages(pdf: Path, layout: bool) -> list[str]:
    args = ["pdftotext", "-enc", "UTF-8"] + (["-layout"] if layout else []) + [str(pdf), "-"]
    text = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    # typographic ligature glyphs (U+FB00-FB06) become plain letters; U+FFFD is left for repair()
    text = "".join(unicodedata.normalize("NFKC", c) if "ﬀ" <= c <= "ﬆ" else c for c in text)
    return text.split("\f")


def clean_lines(page: str) -> list[str]:
    return [re.sub(r"\s{2,}", " ", line).strip() for line in page.splitlines()]


EDGE = 2  # running headers/footers live in a page's first and last two non-empty lines (3 would take the guide's "TAXA" line, which repeats on most pages)


def edges(lines: list[str]) -> set[int]:
    filled = [i for i, line in enumerate(lines) if line]
    return set(filled[:EDGE] + filled[-EDGE:])


def running_lines(all_pages: list[list[str]]) -> set[str]:
    """Edge lines (digits masked) present at the edge of at least 30% of the pages.

    Only page edges count: a field label repeated inside every page (TAXA, REQUISITOS) is
    content, not a running header.
    """
    seen = collections.Counter()
    for lines in all_pages:
        seen.update({re.sub(r"\d+", "#", lines[i]) for i in edges(lines)})
    return {k for k, v in seen.items() if v >= 0.3 * len(all_pages)}


ARTICLE_LABEL = re.compile(r"^(Art\.?\s*\d+[ºo°]?(?:-[A-Z])?)\s*(.*)$")


def lift_labels(lines: list[str]) -> list[str]:
    """Move an article label printed on a paragraph's second line back to its start.

    In the IPLAM PDF the label of some multi-line articles is centered beside the text, so
    the layout extraction puts it between the first and second lines ("...proposta do
    Prefeito, de" / "Art. 31" / "pelo menos um terço..."). 19 articles in the Lei Orgânica.
    """
    out = list(lines)
    for i in range(1, len(out)):
        m = ARTICLE_LABEL.match(out[i])
        prev = out[i - 1]
        starts_paragraph = i < 2 or not out[i - 2]
        if (m and prev and starts_paragraph and not re.search(r"[.:;]$", prev)
                and not NEW_UNIT.match(prev) and not TITLE.match(prev)):
            out[i - 1] = f"{m.group(1)} {prev}"
            out[i] = m.group(2) or None  # a label alone on its line leaves nothing behind
    return [line for line in out if line is not None]


def join_wrapped(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        prev = out[-1] if out else ""
        if prev and prev.endswith("-") and line[:1].islower():
            out[-1] = prev[:-1] + line
        elif prev and not re.search(r"[.:;!?]$", prev) and not NEW_UNIT.match(line) and not TITLE.match(prev):
            out[-1] = prev + " " + line
        else:
            out.append(line)
    return out


def vocabulary(*texts: str) -> collections.Counter:
    words = collections.Counter()
    for t in texts:
        words.update(w.lower() for w in re.findall(r"[^\W\d_]+", t) if "�" not in w)
    return words


def repair(text: str, vocab: collections.Counter, unresolved: set[str]) -> str:
    def fix(match: re.Match) -> str:
        word = match.group(0)
        parts = word.split("�")
        best, best_n = None, 0
        for combo in itertools.product(LIGATURES, repeat=len(parts) - 1):
            cand = parts[0] + "".join(c + p for c, p in zip(combo, parts[1:]))
            n = vocab.get(cand.lower(), 0)
            if n > best_n:
                best, best_n = cand, n
        if best is None:
            unresolved.add(word)
            best = word.replace("�", "ti")
        return best
    return re.sub(r"[^\W\d_]*�[\w�]*", fix, text)


def convert(pdf: Path, layout: bool, vocab: collections.Counter | None = None,
            unresolved: set[str] | None = None) -> str:
    raw = [clean_lines(p) for p in pages(pdf, layout)]
    if layout:
        raw = [lift_labels(lines) for lines in raw]
    drop = running_lines(raw)
    kept: list[str] = []
    for lines in raw:
        edge = edges(lines)
        kept += [l for i, l in enumerate(lines)
                 if not (i in edge and (re.sub(r"\d+", "#", l) in drop or re.fullmatch(r"\d+", l)))
                 and "leismunicipais.com.br" not in l.lower()]
        kept.append("")
    text = "\n".join(join_wrapped(kept)).strip() + "\n"
    if vocab is not None:
        text = repair(text, vocab, unresolved)
    return re.sub(r"\n{3,}", "\n\n", text)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    guia = convert(FONTES / "guia_de_servicos_segov.pdf", layout=False)
    (OUT / "atendimento_maceio_01_guia_de_servicos.md").write_text(guia, encoding="utf-8")
    dhnet = "\n".join(pages(FONTES / "lei_organica_maceio_dhnet_2007.pdf", layout=False))
    iplam = "\n".join(pages(FONTES / "lei_organica_maceio_iplam.pdf", layout=True))
    unresolved: set[str] = set()
    lei = convert(FONTES / "lei_organica_maceio_iplam.pdf", layout=True,
                  vocab=vocabulary(dhnet, guia, iplam), unresolved=unresolved)
    (OUT / "atendimento_maceio_02_lei_organica.md").write_text(lei, encoding="utf-8")
    (HERE / "ligaduras_nao_resolvidas.txt").write_text("\n".join(sorted(unresolved)) + "\n", encoding="utf-8")
    for name, t in (("guia", guia), ("lei", lei)):
        print(f"{name}: {len(t):,} chars, {t.count(chr(10) + chr(10)) + 1} paragraphs, "
              f"U+FFFD left: {t.count(chr(0xfffd))}")
    print(f"unresolved ligature words: {len(unresolved)}")


if __name__ == "__main__":
    main()
