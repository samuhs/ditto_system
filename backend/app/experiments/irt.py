"""Item response theory over an experiment: questions as items, configurations as respondents.

A Rasch (1PL) model, P(good answer) = sigmoid(ability_j - difficulty_i), fitted
to continuous scores in [0, 1] used as soft Bernoulli targets (as Beta/continuous
IRT variants allow; cf. Guinet et al., ICML 2024, arXiv 2405.13622, which fits IRT
with RAG configurations as respondents). Difficulties are centred at 0: a positive
value is harder than the average question of this experiment, so values are only
comparable within one fit. A small L2 penalty keeps questions that every
configuration got fully right (or wrong) finite.
"""
import numpy as np

# Below this many questions the estimates are only indicative. A design estimate
# (docs/research/2026-09-25-dificuldade-da-pergunta.md, section 5.4), not a
# number from the literature.
MIN_RELIABLE_QUESTIONS = 50

_ITERATIONS = 200
_L2 = 0.1
_MAX_STEP = 1.0


def fit_rasch(
    responses: dict[tuple[str, str], float],
) -> tuple[dict[str, float], dict[str, float]]:
    """Fit {(respondent, item): score} and return (difficulty per item, ability per respondent).

    Repeated (respondent, item) pairs are averaged. Uses diagonal Newton steps
    on the penalised log-likelihood, re-centring the difficulties each step.
    """
    if not responses:
        return {}, {}
    respondents = sorted({r for r, _ in responses})
    items = sorted({i for _, i in responses})
    r_index = {r: k for k, r in enumerate(respondents)}
    i_index = {i: k for k, i in enumerate(items)}
    total = np.zeros((len(respondents), len(items)))
    count = np.zeros_like(total)
    for (respondent, item), score in responses.items():
        total[r_index[respondent], i_index[item]] += min(1.0, max(0.0, score))
        count[r_index[respondent], i_index[item]] += 1
    observed = count > 0
    y = np.divide(total, count, out=np.zeros_like(total), where=observed)

    ability = np.zeros(len(respondents))
    difficulty = np.zeros(len(items))
    def gradients():
        p = 1 / (1 + np.exp(-(ability[:, None] - difficulty[None, :])))
        return np.where(observed, y - p, 0.0), np.where(observed, p * (1 - p), 0.0)

    for _ in range(_ITERATIONS):
        # Alternate the two blocks and cap each step: joint steps overshoot.
        residual, information = gradients()
        step = (residual.sum(1) - _L2 * ability) / (information.sum(1) + _L2)
        ability += np.clip(step, -_MAX_STEP, _MAX_STEP)
        residual, information = gradients()
        step = (residual.sum(0) + _L2 * difficulty) / (information.sum(0) + _L2)
        difficulty -= np.clip(step, -_MAX_STEP, _MAX_STEP)
        shift = difficulty.mean()
        difficulty -= shift
        ability -= shift
    return (
        {item: float(difficulty[k]) for item, k in i_index.items()},
        {respondent: float(ability[k]) for respondent, k in r_index.items()},
    )
