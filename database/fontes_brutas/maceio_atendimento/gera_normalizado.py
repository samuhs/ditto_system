"""B3 (normalized version): the same facts as the raw version, in self-contained '###' blocks.

Follows database/DIRETRIZES.md (sections 2-6): a context block on top; one '###' unit per
topic, no blank line inside, up to ~800 characters; the header names the entity (the
service and "Prefeitura de Maceió", or the article of the "Lei Orgânica do Município de
Maceió"). The text of each field is copied, never rewritten, so evidence passages taken
from the raw version also match here. Scripted rather than hand-edited, so the level is
reproducible (DIRETRIZES section 11). Run after gera_bruto.py, from the repository root:

    python3 database/fontes_brutas/maceio_atendimento/gera_normalizado.py
"""
import difflib
import re
import subprocess
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "maceio_atendimento"
LIMIT = 800
GUIDE_PDF = HERE / "fontes" / "guia_de_servicos_segov.pdf"
LABELS = {
    "INFORMAÇÕES DO SERVIÇO": "info", "INFORMAÇÕES SOBRE O SERVIÇO": "info",
    "ROTEIRO PARA ATENDIMENTO AO CIDADÃO": "roteiro", "ROTEIRO": "roteiro",
    "REQUISITOS PARA O REQUERIMENTO": "requisitos", "REQUISITOS PARA FUTURA INSCRIÇÃO": "requisitos",
    "REQUISITOS PARA O PARTICIPAR DO PRORAMA": "requisitos",
    "OBSERVAÇÕES": "observacoes", "TAXA": "taxa", "TAXA DE VISTORIA": "taxa",
}
SKIP = {"FICHA TÉCNICA", "SERVIÇOS DE BALCÃO - SUBPREFEITURA", "SERVIÇO", "ÓRGÃO", "RESPONSÁVEL",
        "Secretaria Municipal de Governo e de Subprefeituras - SEGOV", "Versão 01"}
CONTEXT_GUIDE = ("# Guia de Serviços da Prefeitura de Maceió\n\n"
                 "Serviços de balcão das subprefeituras de Maceió (AL), da Carta de Serviços ao Usuário "
                 "publicada pela Secretaria Municipal de Governo e de Subprefeituras (SEGOV), versão 01. "
                 "Informações reunidas em outubro de 2026.\n")
CONTEXT_LAW = ("# Lei Orgânica do Município de Maceió\n\n"
               "Texto consolidado da Lei Orgânica do Município de Maceió (AL), na compilação publicada pelo "
               "IPLAM. Informações reunidas em outubro de 2026.\n")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"\W+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def pdf_pages(pdf: Path) -> list[list[str]]:
    text = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"], capture_output=True,
                          text=True, check=True).stdout
    text = "".join(unicodedata.normalize("NFKC", c) if "ﬀ" <= c <= "ﬆ" else c for c in text)
    return [[re.sub(r"\s+", " ", l).strip() for l in p.splitlines()] for p in text.split("\f")]


def join(lines: list[str]) -> list[str]:
    """Join wrapped lines; a numbered step or a line after a full stop starts a new line."""
    out: list[str] = []
    for line in lines:
        if not line:
            continue
        if out and not re.search(r"[.:;!?]$", out[-1]) and not re.match(r"^(\d+[.)-]|[a-z]\)|[-•])\s", line):
            out[-1] = (out[-1][:-1] if out[-1].endswith("-") and line[:1].islower() else out[-1] + " ") + line
        else:
            out.append(line)
    return out


def summary_names(pages: list[list[str]]) -> list[tuple[str, str]]:
    """(agency acronym, service name in normal case) pairs from the guide's table of contents."""
    lines = [l for p in pages[:4] for l in p if l and l not in ("SUMÁRIO", "GUIA DE SERVIÇOS")]
    pairs = []
    for a, b in zip(lines, lines[1:]):
        if re.fullmatch(r"[A-Z]{2,}", a) and not re.fullmatch(r"[A-Z]{2,}", b):
            pairs.append((a, b))
    return pairs


def pack(header: str, lines: list[str]) -> list[str]:
    """One or more blocks of at most LIMIT characters, each with its own header."""
    blocks, cur = [], []
    for line in lines:
        if cur and len(header) + 12 + sum(len(x) + 1 for x in cur) + len(line) > LIMIT:
            blocks.append(cur)
            cur = []
        cur.append(line)
    if cur:
        blocks.append(cur)
    if len(blocks) == 1:
        return [f"### {header}\n" + "\n".join(blocks[0])]
    return [f"### {header} (parte {i})\n" + "\n".join(b) for i, b in enumerate(blocks, 1)]


def guide() -> tuple[str, list[str]]:
    pages = pdf_pages(GUIDE_PDF)
    names = summary_names(pages)
    blocks, report = [], []
    for page in pages:
        if "FICHA TÉCNICA" not in page:
            continue
        i = page.index("SERVIÇO") + 1
        title_lines = []
        while i < len(page) and page[i] not in LABELS and page[i]:
            title_lines.append(page[i])
            i += 1
        title = " ".join(title_lines)
        organ_label_in_title = title.endswith("ÓRGÃO RESPONSÁVEL")
        title = title.removesuffix("ÓRGÃO RESPONSÁVEL").strip()
        # a generic sheet title ("MULTA DE TRÂNSITO") covers several services of the table of
        # contents; only a close match names one service, otherwise the sheet's own title is used
        match = difflib.get_close_matches(norm(title), [norm(n) for _, n in names], n=1, cutoff=0.9)
        if match:
            agency, name = next((a, n) for a, n in names if norm(n) == match[0])
        else:
            close = difflib.get_close_matches(norm(title), [norm(n) for _, n in names], n=1, cutoff=0.5)
            agency = next((a for a, n in names if close and norm(n) == close[0]), "")
            name = title.capitalize()
            report.append(f"sheet title kept (no single service): {title}")
        fields: dict[str, list[str]] = {}
        current = previous = None
        after_taxa = False
        organ: list[str] = []
        in_organ = organ_label_in_title
        for line in page[i:]:
            if line.rstrip(":").strip() in LABELS:
                line = line.rstrip(":").strip()
                previous, current = current, LABELS[line]
                after_taxa = False
                continue
            if line == "RESPONSÁVEL":
                in_organ = True
                continue
            if line in SKIP or not line:
                if not line and current == "taxa" and fields.get("taxa"):
                    after_taxa = True
                if not line:
                    in_organ = False
                continue
            if in_organ:
                organ.append(line)
                continue
            target = previous if (current == "taxa" and after_taxa and previous) else current
            if target:
                fields.setdefault(target, []).append(line)
        organ_text = " ".join(organ)
        who = f"{name} na Prefeitura de Maceió" + (f" ({agency})" if agency else "")
        info = join(fields.get("info", []))
        if organ_text:
            info = [f"Órgão responsável: {organ_text}."] + info
        blocks += pack(f"{who}: o que é e órgão responsável", info)
        if fields.get("roteiro"):
            blocks += pack(f"{who}: como é feito o atendimento", join(fields["roteiro"]))
        req = join(fields.get("requisitos", []))
        taxa = join(fields.get("taxa", []))
        if req or taxa:
            blocks += pack(f"{who}: requisitos e taxa",
                           (["Requisitos para o requerimento:"] + req if req else []) + (["Taxa: " + " ".join(taxa)] if taxa else []))
        if fields.get("observacoes"):
            blocks += pack(f"{who}: observações", join(fields["observacoes"]))
    # the table of contents is content too (which agency offers which service): one block per agency
    by_agency: dict[str, list[str]] = {}
    for agency, name in names:
        by_agency.setdefault(agency, []).append(name)
    toc = []
    for agency, services in by_agency.items():
        toc += pack(f"Serviços de balcão do órgão {agency} nas subprefeituras de Maceió",
                    [f"Serviços do órgão {agency} oferecidos nas subprefeituras da Prefeitura de Maceió:"]
                    + [f"- {s}" for s in services])
    return CONTEXT_GUIDE + "\n" + "\n\n".join(toc + blocks) + "\n", report


def sentence_case(s: str) -> str:
    s = s.strip().lower()
    return s[:1].upper() + s[1:]


def law() -> tuple[str, list[str]]:
    raw = (OUT / "atendimento_maceio_02_lei_organica.md").read_text(encoding="utf-8")
    paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
    blocks, report = [], []
    section, adt = "", False
    art, body = None, []

    def flush():
        if art is None:
            return
        where = " das Disposições Transitórias" if adt else ""
        topic = f" ({section})" if section else ""
        lines = [l for p in body for l in p.splitlines()]
        blocks.extend(pack(f"Lei Orgânica do Município de Maceió{where}, art. {art}{topic}", join(lines)))

    heading = re.compile(r"^(TÍTULO|CAPÍTULO|SE[CÇ]+ÃO|Se[cç]+ão|SUBSE[CÇ]+ÃO|Subse[cç]+ão)\s+[IVXLC]+\b\s*(.*)$")
    for p in paras:
        first = p.splitlines()[0]
        m_head = heading.match(first)
        is_caps_name = re.fullmatch(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ ,-]{4,}", p) is not None and not p.startswith("LEI ORGÂNICA")
        if m_head or is_caps_name or first.startswith("ATO DAS DISPOSI"):
            flush()
            art, body = None, []
            if first.startswith("ATO DAS DISPOSI"):
                adt = True
            lines = p.splitlines()
            name = (m_head.group(2) if m_head and m_head.group(2) else
                    lines[1] if m_head and len(lines) > 1 else p if is_caps_name else "")
            if name:
                section = sentence_case(name)
            continue
        m = re.match(r"^Art\.?\s*(\d+[ºo°]?(?:-[A-Z])?)\.?\s*", p)
        if m:
            flush()
            art, body = m.group(1).replace("o", "º").replace("°", "º"), [p]
        elif len(p) < 60 and "\n" not in p and not re.search(r"[.:;]$", p) and re.match(r"^D[aeo]s? ", p):
            flush()  # a mixed-case section name ("Da Educação")
            art, body = None, []
            section = sentence_case(p)
        elif art is not None:
            body.append(p)
        elif not blocks and not p.startswith("LEI ORGÂNICA"):
            blocks.append("### Lei Orgânica do Município de Maceió: preâmbulo\n" + " ".join(p.splitlines()))
        elif not p.startswith("LEI ORGÂNICA"):
            report.append(f"text outside any article: {p[:80]}")
    flush()
    return CONTEXT_LAW + "\n" + "\n\n".join(blocks) + "\n", report


def main() -> None:
    for name, (text, report) in (("atendimento_maceio_01_guia_de_servicos_normalizado.md", guide()),
                                 ("atendimento_maceio_02_lei_organica_normalizado.md", law())):
        (OUT / name).write_text(text, encoding="utf-8")
        units = [b for b in text.split("\n\n") if b.startswith("###")]
        big = [b.splitlines()[0] for b in units if len(b) > LIMIT]
        print(f"{name}: {len(text):,} chars, {len(units)} blocks, {len(big)} over {LIMIT} chars")
        for line in report[:10] + big[:10]:
            print("   ", line)


if __name__ == "__main__":
    main()
