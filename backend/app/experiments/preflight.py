"""Memory checks run before an experiment starts; they warn, never block."""
from collections.abc import Callable

from app.core.memory.manager import is_local_embedding
from app.core.memory.profile import MemoryProfile
from app.experiments.schemas import ExperimentConfig, index_pairs


def memory_warnings(
    config: ExperimentConfig,
    profile: MemoryProfile,
    is_local: Callable[[str], bool] = is_local_embedding,
) -> list[str]:
    """PT-BR warnings about limits this experiment will hit under the profile."""
    warnings: list[str] = []
    eval_name = config.eval_embedding
    retrieval_locals = sorted({e for _, e in index_pairs(config) if is_local(e) and e != eval_name})
    if is_local(eval_name) and retrieval_locals and profile.max_local_models < 2:
        warnings.append(
            f"O embedding de avaliação ({eval_name}) e o de busca ({', '.join(retrieval_locals)}) "
            f"são modelos locais diferentes e ficarão carregados juntos, acima do limite de "
            f"{profile.max_local_models} modelo local do perfil {profile.name}. Para economizar "
            f"memória, use o mesmo embedding na busca e na avaliação."
        )
    if config.concurrency > profile.max_concurrency:
        warnings.append(
            f"A concorrência pedida ({config.concurrency}) passa do limite do perfil "
            f"{profile.name}; o experimento vai rodar com {profile.max_concurrency}."
        )
    return warnings
