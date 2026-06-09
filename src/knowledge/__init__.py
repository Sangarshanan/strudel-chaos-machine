"""Static knowledge resources."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).parent


@lru_cache(maxsize=None)
def load_sounds() -> dict:
    """Return the merged sound catalog."""
    with (_HERE / "sounds.json").open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def load_effects() -> dict:
    with (_HERE / "effects.json").open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def load_syntax_md() -> str:
    return (_HERE / "syntax.md").read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def load_patterns_md() -> str:
    return (_HERE / "patterns.md").read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def all_sound_names() -> list[str]:
    """Flat, de-duplicated list of every known sound name."""
    data = load_sounds()
    names: set[str] = set()
    for key in ("synths", "drums", "gm_samples", "vcsl_samples"):
        for n in data.get(key, []):
            names.add(n)
    return sorted(names)


@lru_cache(maxsize=None)
def all_bank_names() -> list[str]:
    return sorted(load_sounds().get("banks", []))


@lru_cache(maxsize=None)
def all_effect_names() -> list[str]:
    """Flat list of every method/effect/transform name."""
    data = load_effects()
    out: set[str] = set()
    for category in data.get("categories", {}).values():
        for entry in category:
            out.add(entry["name"])
    return sorted(out)
