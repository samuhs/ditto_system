"""The Rubrica v1 of the Anotação humana (fixed in code; a Rodada records its version)."""

RUBRIC_VERSION = 1

RUBRIC = {
    "version": RUBRIC_VERSION,
    "dimensions": [
        {
            "key": "correctness",
            "label": "Correção",
            "question": "A resposta está certa, comparada com a resposta de referência?",
            "levels": [
                {"value": 0, "label": "Errada", "description": "Errada ou contradiz a referência."},
                {"value": 1, "label": "Parcial", "description": "Acerta só parte dos fatos da referência."},
                {"value": 2, "label": "Correta", "description": "Correta e completa."},
            ],
        },
        {
            "key": "grounding",
            "label": "Fundamentação",
            "question": "O que a resposta afirma está nos trechos recuperados?",
            "levels": [
                {"value": 0, "label": "Inventa", "description": "Inventa ou contradiz os trechos recuperados."},
                {"value": 1, "label": "Parcial", "description": "Só parte do que afirma está nos trechos."},
                {"value": 2, "label": "Apoiada", "description": "Toda afirmação relevante está nos trechos."},
            ],
        },
    ],
}

DIMENSIONS = tuple(d["key"] for d in RUBRIC["dimensions"])
LEVELS = (0, 1, 2)
