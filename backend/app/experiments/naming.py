"""Random, human-readable experiment name generator."""
import random

_ADJECTIVES = [
    "brave", "calm", "clever", "eager", "gentle",
    "happy", "jolly", "kind", "lively", "proud",
]
_NOUNS = [
    "otter", "falcon", "maple", "river", "comet",
    "willow", "ember", "cedar", "pebble", "heron",
]


def generate_experiment_name() -> str:
    """Return a random name like 'brave-otter-42'."""
    adjective = random.choice(_ADJECTIVES)
    noun = random.choice(_NOUNS)
    return f"{adjective}-{noun}-{random.randint(10, 99)}"
