"""Mutation utilities for enriching Strudel code with effects and BPM changes."""

from __future__ import annotations

import random
import re
from typing import Optional


class EffectLibrary:
    """Curated effects for application to functions."""
    
    # Lightweight, musically useful effects that work reliably
    EFFECTS = {
        "amplitude": [
            ("gain", "(0.3)", "(0.5)", "(0.7)"),
        ],
        "panning": [
            ("pan", "(0.2)", "(0.5)", "(0.8)"),
        ],
        "filters": [
            ("lpf", "(800)", "(1200)", "(2000)"),
            ("hpf", "(100)", "(200)", "(400)"),
        ],
        "playback": [
            ("speed", "(1.5)", "(0.8)", "(1.2)"),
            ("begin", "(0.1)", "(0.2)"),
            ("end", "(0.8)", "(0.9)"),
        ],
        "delays": [
            ("delay", "(0.2)", "(0.4)", "(0.5)"),
            ("delaytime", "(0.25)", "(0.5)"),
        ],
        "reverb": [
            ("room", "(0.3)", "(0.5)", "(0.8)"),
        ],
    }
    
    @classmethod
    def random_effects(cls, count: Optional[int] = None) -> list[tuple[str, str]]:
        """Select 1-3 random effects with random parameters."""
        if count is None:
            count = random.randint(1, 3)
        
        effects = []
        categories = list(cls.EFFECTS.keys())
        
        for _ in range(count):
            category = random.choice(categories)
            effect_name, *params = random.choice(cls.EFFECTS[category])
            param = random.choice(params)
            effects.append((effect_name, param))
        
        return effects


def apply_effects_to_function(func_call: str, effects: list[tuple[str, str]]) -> str:
    """
    Apply effects to a function call, chaining them.
    
    E.g., s("bd").gain(0.5).delay(0.3)
    """
    result = func_call.rstrip(")")
    for effect_name, param in effects:
        result += f".{effect_name}{param}"
    
    # Close the chain if needed
    if not result.endswith(")"):
        result += ")"
    
    return result


def maybe_add_effects(
    buffer: str,
    chance: float = 0.6,
    count: Optional[int] = None,
    preserve_existing: Optional[bool] = None,
) -> str:
    """
    Randomly add effects to functions in the buffer.
    
    Args:
        buffer: Strudel code string
        chance: Probability (0-1) of adding effects
        count: Number of effects to add (None = random 1-3)
        preserve_existing: If None, random. If True, always preserve. If False, replace.
    
    Returns:
        Modified buffer with effects applied
    """
    if random.random() > chance:
        return buffer
    
    # Find all s(...) calls (simple heuristic)
    pattern = r's\([^)]*(?:\([^)]*\))*[^)]*\)'
    matches = list(re.finditer(pattern, buffer))
    
    if not matches:
        return buffer
    
    # Randomly select 1-2 functions to modify
    num_to_modify = random.randint(1, min(2, len(matches)))
    indices_to_modify = random.sample(range(len(matches)), num_to_modify)
    
    effects_list = EffectLibrary.random_effects(count)
    
    # Build new buffer with effects
    new_buffer = buffer
    offset = 0
    
    for idx in sorted(indices_to_modify):
        match = matches[idx]
        start = match.start() + offset
        end = match.end() + offset
        
        original = new_buffer[start:end]
        
        # Decide whether to preserve existing effects
        should_preserve = preserve_existing if preserve_existing is not None else random.choice([True, False])
        
        if should_preserve and "." in original:
            # Already has effects, don't add more
            continue
        
        modified = apply_effects_to_function(original, effects_list)
        new_buffer = new_buffer[:start] + modified + new_buffer[end:]
        offset += len(modified) - len(original)
    
    return new_buffer


def add_function_prefix(buffer: str, prefix: str = "drums") -> str:
    """
    Prefix functions with a named variable.
    
    E.g., s(...).stack(...) becomes
    $drums: s(...).stack(...)
    """
    # Only add prefix if not already present
    if buffer.startswith("$"):
        return buffer
    
    # Simple approach: wrap the whole thing
    return f"${prefix}: {buffer}"


def maybe_update_bpm(
    buffer: str,
    current_cps: Optional[float] = None,
    chance: float = 0.4,
) -> str:
    """
    Randomly add or modify a setcps() call for BPM changes.
    
    Args:
        buffer: Strudel code
        current_cps: Current CPS value (0.5-2), None = random
        chance: Probability of updating BPM
    
    Returns:
        Modified buffer with optional setcps() call
    """
    if random.random() > chance:
        return buffer
    
    # Determine new CPS
    if current_cps is None:
        current_cps = random.uniform(0.5, 2.0)
    
    # Change by ±0.2 to 0.5
    change = random.uniform(-0.5, 0.5)
    new_cps = max(0.5, min(2.0, current_cps + change))
    new_cps = round(new_cps, 2)
    
    # Remove existing setcps call if present
    buffer = re.sub(r'setcps\([^)]*\);?\s*', '', buffer)
    
    # Add new setcps at the beginning
    return f"setcps({new_cps});\n{buffer}"


def enrich_buffer(
    buffer: str,
    add_prefix: bool = True,
    add_effects: bool = True,
    update_bpm: bool = True,
    current_cps: Optional[float] = None,
    function_prefix: str = "drums",
) -> str:
    """
    Enrich a buffer with prefix, effects, and BPM changes.
    
    This is the main entry point for mutation enhancement.
    """
    result = buffer
    
    if add_effects:
        result = maybe_add_effects(result, chance=0.6)
    
    if update_bpm:
        result = maybe_update_bpm(result, current_cps=current_cps, chance=0.4)
    
    if add_prefix:
        result = add_function_prefix(result, prefix=function_prefix)
    
    return result


def extract_cps_from_buffer(buffer: str) -> Optional[float]:
    """Extract setcps value from buffer if present."""
    match = re.search(r'setcps\(([0-9.]+)\)', buffer)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None
