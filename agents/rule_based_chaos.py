"""Rule-based chaos engine: mutates Strudel buffers without an LLM.

On every tick exactly two operations are chosen at random from:
  1. pattern_mutation  – apply a mini-notation trick inside note/s/sound calls
  2. effects_change    – add or remove one or more chainable effects
  3. bpm_change        – adjust or introduce setcps() / setcpm()

Mini-notation operations available for pattern_mutation:
  sub_sequence      – group two tokens into [a b]
  angle_brackets    – wrap a slice in <...> for slow cycling
  multiply          – add *N repetition to a token
  divide            – wrap a group in [...]/N (spans N cycles)
  elongate          – add @N weight to a token
  replicate         – add !N shorthand replication to a token
  shuffled_parallel – clone the pattern as a parallel voice with tokens reordered
  parallel          – add a new comma-separated parallel voice from the sound pool
  alternate         – replace a token with tok | other (random alternation)
  degrade           – add ? or ?prob randomised dropout to a token
"""

from __future__ import annotations

import logging
import random
import re
from typing import Optional

log = logging.getLogger(__name__)

# ── Note vocabulary ───────────────────────────────────────────────────────────
_NOTES = ["c", "d", "e", "f", "g", "a", "b", "eb", "bb", "db", "gb", "ab"]



# ── Mini-notation tokeniser ───────────────────────────────────────────────────

def _tokenize(pattern: str) -> list[str]:
    """Split a mini-notation string on spaces, keeping bracket groups intact.
    
    Modifiers (like *2, @3) and euclidean params (like (3,8)) remain attached
    to their root tokens.
    """
    tokens: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in pattern:
        if ch in "([<":
            depth += 1
            current.append(ch)
        elif ch in ")]>":
            depth -= 1
            current.append(ch)
        elif ch == " " and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current))
    return [t for t in tokens if t]


def _untokenize(tokens: list[str]) -> str:
    return " ".join(tokens)


# ── Individual pattern transforms ─────────────────────────────────────────────
# Each op: (tokens, sounds) -> (new_tokens, description, changed)

def _op_sub_sequence(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Group two adjacent tokens into [a b].

    Only considers adjacent pairs where both tokens are valid pattern atoms
    (i.e. neither starts with a bare modifier character like */@!?).  This
    prevents invalid groupings such as [[bd hh] *3(3,8)] that arise when a
    previous operation left orphaned modifier tokens in the token list.
    """
    _MODIFIER_PREFIX = re.compile(r'^[*/@!?]')
    valid = {k for k in range(len(tokens)) if not _MODIFIER_PREFIX.match(tokens[k])}
    # Candidate starting indices where tokens[i] AND tokens[i+1] are both valid.
    candidates = [i for i in valid if (i + 1) in valid]
    if not candidates:
        return tokens, "", False
    i = random.choice(candidates)
    grouped = f"[{tokens[i]} {tokens[i + 1]}]"
    return (
        tokens[:i] + [grouped] + tokens[i + 2:],
        f"sub-sequence [{tokens[i]} {tokens[i + 1]}]",
        True,
    )


def _op_angle_brackets(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Wrap a slice of tokens in <...> for slow cycling."""
    if len(tokens) < 2:
        return tokens, "", False
    start = random.randint(0, len(tokens) - 2)
    end = random.randint(start + 2, min(start + 5, len(tokens) + 1))
    inner = " ".join(tokens[start:end])
    grouped = f"<{inner}>"
    return (
        tokens[:start] + [grouped] + tokens[end:],
        f"slow-cycle <{inner}>",
        True,
    )


def _op_multiply(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Add *N repetition to a random token."""
    n = random.choice([2, 3, 4])
    i = random.randint(0, len(tokens) - 1)
    base = re.sub(r'\*\d+$', '', tokens[i])
    new_tokens = tokens[:]
    new_tokens[i] = f"{base}*{n}"
    return new_tokens, f"multiply {base}*{n}", True


def _op_divide(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Wrap a group in [...]/N so it spans N cycles."""
    n = random.choice([2, 3])
    if len(tokens) == 1:
        return [f"[{tokens[0]}]/{n}"], f"divide /{n}", True
    start = random.randint(0, len(tokens) - 2)
    end = random.randint(start + 1, min(start + 3, len(tokens)))
    inner = " ".join(tokens[start:end])
    new_token = f"[{inner}]/{n}"
    return tokens[:start] + [new_token] + tokens[end:], f"divide group /{n}", True


def _op_elongate(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Add @N weight to a random token."""
    n = random.choice([2, 3])
    i = random.randint(0, len(tokens) - 1)
    base = re.sub(r'@\d+$', '', tokens[i])
    new_tokens = tokens[:]
    new_tokens[i] = f"{base}@{n}"
    return new_tokens, f"elongate {base}@{n}", True


def _op_replicate(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Replicate a token with token!N shorthand."""
    n = random.choice([2, 3])
    i = random.randint(0, len(tokens) - 1)
    base = re.sub(r'!\d+$', '', tokens[i])
    new_tokens = tokens[:]
    new_tokens[i] = f"{base}!{n}"
    return new_tokens, f"replicate {base}!{n}", True


def _op_shuffled_parallel(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Clone the current pattern as a parallel voice with tokens reordered.

    For example ``[bd <hh oh>]`` becomes
    ``[bd <hh oh>], [<hh oh> bd]`` — the second voice is a shuffled copy
    of the first, guaranteed to have a different order when len >= 2.
    """
    if len(tokens) < 2:
        return tokens, "", False

    shuffled = tokens[:]
    # Guarantee a different ordering by shuffling until it differs.
    for _ in range(10):
        random.shuffle(shuffled)
        if shuffled != tokens:
            break

    voice = _untokenize(shuffled)
    return (
        tokens + [f"__PARALLEL__{voice}"],
        f"shuffled parallel: {voice}",
        True,
    )



def _op_parallel(
    tokens: list[str], sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Schedule a parallel voice via comma syntax (sentinel for post-processing)."""
    n_notes = random.randint(2, 4)
    pool = sounds if sounds else _NOTES
    voice = " ".join(random.choices(pool, k=n_notes))
    return tokens + [f"__PARALLEL__{voice}"], f"parallel voice: {voice}", True


def _op_alternate(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Replace one token with '[tok | other]' random alternation.

    Only tokens that are actual sound/note atoms (not bare arithmetic modifiers
    such as *2, /2, @3, !2, ?0.5) are eligible, to avoid invalid syntax like
    '[bd] | *2 *2'.
    """
    # A token is a valid alternation candidate if it starts with a letter,
    # digit, or an opening bracket – not with an arithmetic/modifier character.
    _MODIFIER_PREFIX = re.compile(r'^[*/@!?]')

    candidates = [
        k for k in range(len(tokens))
        if not _MODIFIER_PREFIX.match(tokens[k])
    ]
    if len(candidates) < 2:
        return tokens, "", False

    i = random.choice(candidates)
    j = random.choice([k for k in candidates if k != i])
    new_tokens = tokens[:]
    # Wrap in [...] so the alternation is unambiguously grouped
    new_tokens[i] = f"[{tokens[i]} | {tokens[j]}]"
    return new_tokens, f"alternate [{tokens[i]} | {tokens[j]}]", True


def _op_degrade(
    tokens: list[str], _sounds: list[str]
) -> tuple[list[str], str, bool]:
    """Add ? dropout to a random token (Strudel mini-notation: token?)."""
    i = random.randint(0, len(tokens) - 1)
    base = re.sub(r'\?$', '', tokens[i])  # strip existing ? if already present
    new_tokens = tokens[:]
    new_tokens[i] = f"{base}?"
    return new_tokens, f"degrade {base}?", True


_PATTERN_OPS = [
    _op_sub_sequence,
    _op_angle_brackets,
    _op_multiply,
    _op_divide,
    _op_elongate,
    _op_replicate,
    _op_shuffled_parallel,
    _op_parallel,
    _op_alternate,
    _op_degrade,
]

# Maximum number of comma-separated parallel voices allowed in a pattern call.
_MAX_PATTERN_VOICES: int = 3
# Maximum number of opening bracket chars ([, <) in a single voice before
# nesting-adding ops are suppressed.
_MAX_PATTERN_COMPLEXITY: int = 4

# Ops that grow the voice count (comma-separated parallel voices).
_ADDITIVE_VOICE_OPS = frozenset([_op_parallel, _op_shuffled_parallel])
# Ops that increase nesting depth / bracket complexity.
_ADDITIVE_NESTING_OPS = frozenset([_op_sub_sequence, _op_angle_brackets, _op_divide, _op_alternate])


def _pattern_complexity(voice: str) -> int:
    """Count opening bracket characters as a proxy for nesting depth."""
    return sum(1 for ch in voice if ch in '[<')


# ── Named-function helpers ────────────────────────────────────────────────────
# Strudel buffers can contain named blocks like:
#   drums: s("bd sd")
#   melody: note("c e g")
# We detect these so we can report *which* function is being mutated.

# Matches 'label:' at the start of a logical line (after newline or start-of-string).
# Group 1 = the label name; Group 2 = start offset of everything that follows.
_FUNC_LABEL_RE = re.compile(r'(?:^|\n)([A-Za-z_][A-Za-z0-9_]*)\s*:', re.MULTILINE)


def _parse_function_names(buffer: str) -> list[tuple[str, int]]:
    """Return [(name, char_offset), ...] for every named function in the buffer.

    The char_offset is the position where the label's body begins (i.e. just
    after the colon), so we can later look up which function owns a given edit.
    """
    results: list[tuple[str, int]] = []
    for m in _FUNC_LABEL_RE.finditer(buffer):
        name = m.group(1)
        body_start = m.end()  # character right after the colon
        results.append((name, body_start))
    return results


def _owning_function(buffer: str, edit_offset: int) -> str:
    """Return the label of the named function that contains edit_offset.

    If no named function is found, returns '<unnamed>'.
    """
    funcs = _parse_function_names(buffer)
    if not funcs:
        return "<unnamed>"
    # Build boundaries: each function's body runs from its body_start up to
    # the body_start of the next function (or end of buffer).
    owner = "<unnamed>"
    for i, (name, body_start) in enumerate(funcs):
        next_start = funcs[i + 1][1] if i + 1 < len(funcs) else len(buffer)
        if body_start <= edit_offset < next_start:
            owner = name
            break
    return owner


# ── Pattern mutation ──────────────────────────────────────────────────────────
# Matches note("..."), s("..."), sound("...") – captures function name and quoted arg
_PATTERN_RE = re.compile(
    r'(note|s|sound)\s*\(\s*(["\'])([^"\']*?)\2\s*\)',
    re.DOTALL | re.IGNORECASE,
)


def _sounds_for_chain(
    buffer: str, chain_start: int, sounds: list[str]
) -> tuple[list[str], bool]:
    """Return (sound_list, bank_active) for the expression ending at chain_start.

    Walks the chained method calls immediately following chain_start.  If a
    ``.bank("X")`` call is present the returned list contains the **bare** voice
    names for that bank (e.g. ``"rolandtr909_bd"`` → ``"bd"``), so they can be
    dropped directly into a pattern that already carries the ``.bank()`` context.
    Returns ``(sounds, False)`` when no bank is found or the filter is empty.

    Note: ``_CHAIN_CALL_RE`` is defined later in the file but that is fine—
    this function is only *called* at runtime, after the full module is loaded.
    """
    tail = buffer[chain_start:]
    offset = 0
    for cm in _CHAIN_CALL_RE.finditer(tail):  # noqa: F821  (defined below)
        if cm.start() != offset:
            break
        if cm.group(1) == "bank":
            raw = cm.group(2).strip().strip('"\'')
            if raw:
                # Normalise: lowercase, strip non-alphanumeric → e.g. "rolandtr909"
                prefix = re.sub(r'[^a-z0-9]', '', raw.lower()) + '_'
                filtered = [s for s in sounds if s.startswith(prefix)]
                if filtered:
                    # Strip the bank prefix so tokens are bare ("bd", "sd", ...)
                    bare = [s[len(prefix):] for s in filtered]
                    log.debug(
                        "[mutate_pattern] bank '%s' detected — %d bare sounds available "
                        "(prefix '%s')",
                        raw, len(bare), prefix,
                    )
                    return bare, True
        offset = cm.end()
    return sounds, False


def mutate_pattern(buffer: str, sounds: list[str]) -> tuple[str, str]:
    """Apply one random mini-notation transform to a randomly chosen pattern call.

    Returns (new_buffer, intent_description).
    """
    matches = list(_PATTERN_RE.finditer(buffer))
    if not matches:
        log.debug("[mutate_pattern] no pattern call (note/s/sound) found in buffer")
        return buffer, "no pattern found"

    match = random.choice(matches)
    func_name = match.group(1)
    quote = match.group(2)
    pattern_str = match.group(3)

    owner = _owning_function(buffer, match.start())
    log.debug(
        "[mutate_pattern] editing function '%s' — matched expression: %s(%s%s%s)  (span %d–%d)",
        owner, func_name, quote, pattern_str, quote,
        match.start(), match.end(),
    )

    # Preserve any existing parallel voices
    voices = [v.strip() for v in pattern_str.split(",")]
    primary_voice = voices[0]
    extra_voices = voices[1:]

    tokens = _tokenize(primary_voice)
    if not tokens:
        log.debug("[mutate_pattern] pattern tokenised to empty list — skipping")
        return buffer, "empty pattern"

    log.debug("[mutate_pattern] tokens before op: %s", tokens)

    # Restrict the sound pool to the active bank when .bank("X") is chained.
    # effective_sounds contains bare names ("bd", "sd") when bank_active is True.
    effective_sounds, bank_active = _sounds_for_chain(buffer, match.end(), sounds)

    # ── Op pool filtering: suppress additive ops once caps are reached ────────
    n_voices = len(voices)
    complexity = _pattern_complexity(primary_voice)
    available_ops = list(_PATTERN_OPS)

    if n_voices >= _MAX_PATTERN_VOICES:
        available_ops = [op for op in available_ops if op not in _ADDITIVE_VOICE_OPS]
        log.debug(
            "[mutate_pattern] voice cap reached (%d/%d) — parallel ops suppressed",
            n_voices, _MAX_PATTERN_VOICES,
        )
    if complexity >= _MAX_PATTERN_COMPLEXITY:
        available_ops = [op for op in available_ops if op not in _ADDITIVE_NESTING_OPS]
        log.debug(
            "[mutate_pattern] complexity cap reached (%d/%d) — nesting ops suppressed",
            complexity, _MAX_PATTERN_COMPLEXITY,
        )
    if not available_ops:
        log.debug("[mutate_pattern] all ops suppressed by caps — no change")
        return buffer, "pattern cap reached"

    op = random.choice(available_ops)
    log.debug("[mutate_pattern] chosen op: %s", op.__name__)

    new_tokens, description, changed = op(tokens, effective_sounds)
    if not changed:
        log.debug("[mutate_pattern] op reported no change")
        return buffer, "no change applied"

    log.debug("[mutate_pattern] tokens after op:  %s", new_tokens)
    log.debug("[mutate_pattern] op description:   %s", description)

    # Extract __PARALLEL__ sentinel
    parallel_addition: Optional[str] = None
    filtered_tokens: list[str] = []
    for t in new_tokens:
        if t.startswith("__PARALLEL__"):
            parallel_addition = t[len("__PARALLEL__"):]
        else:
            filtered_tokens.append(t)

    # ── Bank sound swap: opportunistically replace a token from the same bank ──
    # After any successful op, if a bank is active, swap one sound atom for a
    # different bare sound from the same bank.  Only plain atoms are eligible
    # (not bracket groups, not modifier-only tokens).
    _ATOM_RE = re.compile(r'^[A-Za-z0-9]')
    if bank_active and effective_sounds:
        swap_candidates = [
            k for k, t in enumerate(filtered_tokens)
            if _ATOM_RE.match(t) and t.rstrip('?') in effective_sounds
        ]
        if swap_candidates:
            idx = random.choice(swap_candidates)
            old_tok = filtered_tokens[idx]
            bare_old = old_tok.rstrip('?')  # keep ? suffix if present
            alternatives = [s for s in effective_sounds if s != bare_old]
            if alternatives:
                new_sound = random.choice(alternatives)
                # Preserve trailing ? if the original token had one
                new_tok = new_sound + ('?' if old_tok.endswith('?') else '')
                filtered_tokens = filtered_tokens[:]
                filtered_tokens[idx] = new_tok
                description += f" + bank swap {old_tok}→{new_tok}"
                log.debug(
                    "[mutate_pattern] bank sound swap: %s → %s",
                    old_tok, new_tok,
                )

    new_primary = _untokenize(filtered_tokens)
    all_voices = [new_primary] + extra_voices
    if parallel_addition:
        all_voices.append(parallel_addition)

    new_pattern_str = ", ".join(all_voices)
    new_call = f'{func_name}({quote}{new_pattern_str}{quote})'
    new_buffer = buffer[: match.start()] + new_call + buffer[match.end():]

    log.debug("[mutate_pattern] original call : %s", match.group(0))
    log.debug("[mutate_pattern] replaced call : %s", new_call)

    return new_buffer, f"pattern ({func_name}): {description}"


# ── Effects helpers ───────────────────────────────────────────────────────────

# These are pattern-level or structural; not chainable audio effects
_NON_CHAINABLE = {
    "note", "s", "sound", "fast", "slow", "rev", "palindrome", "iter",
    "every", "sometimes", "often", "rarely", "stack", "cat", "seq",
    "chunk", "ply", "bite", "layer", "degradeBy", "jux",
    "struct", "mask", "n", "scale", "transpose", "octave", "bank",
    "striate", "clip"
}

_FALLBACK_EFFECTS: list[dict] = [
    {"name": "gain", "range": [0.2, 1.2]},
    {"name": "pan", "range": [0.0, 1.0]},
    {"name": "lpf", "range": [200, 4000]},
    {"name": "hpf", "range": [50, 800]},
    {"name": "room", "range": [0.1, 0.9]},
    {"name": "delay", "range": [0.1, 0.6]},
    {"name": "delaytime", "range": [0.125, 0.5]},
    {"name": "speed", "range": [0.5, 2.0]},
    {"name": "crush", "range": [2, 12]},
    {"name": "distort", "range": [0.1, 0.8]},
]


def _flatten_effects(effects_knowledge: list | dict) -> list[dict]:
    """Flatten effects.json categories dict or a raw list into a flat list of dicts."""
    if isinstance(effects_knowledge, list):
        return [e for e in effects_knowledge if isinstance(e, dict) and "name" in e]
    if isinstance(effects_knowledge, dict):
        flat: list[dict] = []
        for items in effects_knowledge.get("categories", {}).values():
            for e in items:
                if isinstance(e, dict) and "name" in e:
                    flat.append(e)
        return flat
    return []


def _random_effect_value(effect: dict) -> str:
    """Generate a random parameter value respecting the effect's range or values."""
    if effect.get("name", "").lower() == "degrade":
        return ""
    if "values" in effect:
        return f'"{random.choice(effect["values"])}"'
    if "range" in effect:
        lo, hi = effect["range"]
        if isinstance(lo, float) or isinstance(hi, float):
            return str(round(random.uniform(lo, hi), 2))
        return str(random.randint(int(lo), int(hi)))
    return "0.5"


# Matches a chained method call immediately following a function: .name(args)
_CHAIN_CALL_RE = re.compile(r'\.([a-zA-Z][a-zA-Z0-9_]*)\(([^)]*)\)')
# Matches a top-level note/s/sound/n call (the core function, without trailing chain).
# (?<!\w)       – not preceded by a word char (avoids matching mid-identifier)
# (?!\w)        – the function name must NOT be followed by more word chars,
#                 so 's(' matches but 'setcps(' does not.
_FUNC_CALL_RE = re.compile(r'(?<!\w)(?:note|sound|s|n)(?!\w)\s*\([^)]*(?:\([^)]*\)[^)]*)*\)', re.IGNORECASE)


def change_effects(buffer: str, effects_knowledge: list | dict) -> tuple[str, str]:
    """Add, remove, replace, or tweak chainable effects on a randomly chosen call.

    Hard cap: at most ``_MAX_EFFECTS`` effects are allowed per call.  Once the
    cap is reached only an existing effect is replaced with a different one, or
    its parameter value is re-randomised — no new effects are added beyond the
    limit.

    Returns (new_buffer, intent_description).
    """
    _MAX_EFFECTS = 4

    flat = _flatten_effects(effects_knowledge)
    flat = [e for e in flat if e.get("name") not in _NON_CHAINABLE]
    if not flat:
        log.debug("[change_effects] no effects from knowledge; using fallback list")
        flat = _FALLBACK_EFFECTS

    func_matches = list(_FUNC_CALL_RE.finditer(buffer))
    if not func_matches:
        log.debug("[change_effects] no note/s/sound/n call found in buffer")
        return buffer, "no function found for effects"

    match = random.choice(func_matches)
    owner = _owning_function(buffer, match.start())
    log.debug(
        "[change_effects] editing function '%s' — target expression: %s  (span %d–%d)",
        owner, match.group(0), match.start(), match.end(),
    )

    # Walk the immediately adjacent chained calls after this function
    tail = buffer[match.end():]
    offset = 0
    existing: list[tuple[str, str, int, int]] = []
    for cm in _CHAIN_CALL_RE.finditer(tail):
        if cm.start() != offset:
            break
        abs_start = match.end() + cm.start()
        abs_end = match.end() + cm.end()
        existing.append((cm.group(1), cm.group(2), abs_start, abs_end))
        offset = cm.end()

    log.debug(
        "[change_effects] existing chained effects (%d/%d): %s",
        len(existing), _MAX_EFFECTS,
        [(n, v) for n, v, _, _ in existing] or "(none)",
    )

    at_cap = len(existing) >= _MAX_EFFECTS

    # ── At cap: replace one effect or re-randomise its value ─────────────────
    if at_cap:
        if not existing:
            return buffer, "no effects to modify"

        name, old_val, abs_start, abs_end = random.choice(existing)
        existing_names = {e[0].lower() for e in existing}

        # 50 % chance: swap for a different effect
        if random.random() < 0.5:
            candidates = [e for e in flat if e["name"].lower() not in existing_names]
            if candidates:
                new_eff = random.choice(candidates)
                new_val = _random_effect_value(new_eff)
                new_call = f".{new_eff['name']}({new_val})"
                new_buffer = buffer[:abs_start] + new_call + buffer[abs_end:]
                log.debug(
                    "[change_effects] action: REPLACE .%s(%s) -> %s",
                    name, old_val, new_call,
                )
                return new_buffer, f"replaced .{name}({old_val}) -> {new_call}"

        # Re-randomise value of the chosen effect
        spec = next((e for e in flat if e["name"].lower() == name.lower()), None)
        new_val = _random_effect_value(spec) if spec else old_val
        new_call = f".{name}({new_val})"
        new_buffer = buffer[:abs_start] + new_call + buffer[abs_end:]
        log.debug(
            "[change_effects] action: RETUNE .%s(%s) -> .%s(%s)",
            name, old_val, name, new_val,
        )
        return new_buffer, f"retuned .{name}({old_val}) -> .{name}({new_val})"

    # ── Below cap: remove ~35 % of the time when effects exist ───────────────
    if existing and random.random() < 0.35:
        name, val, abs_start, abs_end = random.choice(existing)
        new_buffer = buffer[:abs_start] + buffer[abs_end:]
        log.debug("[change_effects] action: REMOVE .%s(%s)", name, val)
        return new_buffer, f"removed effect .{name}({val})"

    # ── Below cap: add one new effect ────────────────────────────────────────
    existing_names = {e[0].lower() for e in existing}
    available = [e for e in flat if e["name"].lower() not in existing_names]
    if not available:
        log.debug("[change_effects] all known effects already present — nothing to add")
        return buffer, "no new effects to add"

    eff = random.choice(available)
    val = _random_effect_value(eff)
    new_chain = f".{eff['name']}({val})"
    insert_pos = match.end() + offset
    new_buffer = buffer[:insert_pos] + new_chain + buffer[insert_pos:]
    log.debug("[change_effects] action: ADD %s after position %d", new_chain, insert_pos)
    return new_buffer, f"added effect {new_chain}"


# ── Bank change ─────────────────────────────────────────────────────────────────

# Verified Strudel sample banks (from https://strudel.cc/learn/samples/)
_STRUDEL_BANKS: list[str] = [
    "RolandTR808", "RolandTR909", "RolandTR707", "RolandTR606",
    "AkaiLinn", "AlesisHR16", "Viscount", "EmuDrumulator",
    "KorgKR55", "KorgMiniPops7", "LinndRum", "OberheimDMX",
]

# Matches .bank("BankName") or .bank('BankName')
_BANK_RE = re.compile(r'\.bank\((["\'])([A-Za-z0-9_]+)\1\)', re.IGNORECASE)


def change_bank(buffer: str) -> tuple[str, str]:
    """Replace one .bank("X") call with a different known Strudel bank.

    Returns (new_buffer, intent_description).
    """
    matches = list(_BANK_RE.finditer(buffer))
    if not matches:
        log.debug("[change_bank] no .bank() call found in buffer")
        return buffer, "no bank found"

    match = random.choice(matches)
    quote = match.group(1)
    current_bank = match.group(2).lower()
    owner = _owning_function(buffer, match.start())

    alternatives = [b for b in _STRUDEL_BANKS if b.lower() != current_bank]
    if not alternatives:
        log.debug("[change_bank] no alternative banks available")
        return buffer, "no alternative bank"

    new_bank = random.choice(alternatives)
    new_call = f".bank({quote}{new_bank}{quote})"
    new_buffer = buffer[:match.start()] + new_call + buffer[match.end():]
    log.debug(
        "[change_bank] editing function '%s' — bank %s → %s",
        owner, current_bank, new_bank,
    )
    return new_buffer, f"bank {current_bank} → {new_bank}"


# ── Scale change ─────────────────────────────────────────────────────────────────

_SCALE_ROOTS: list[str] = [
    "C", "C#", "Db", "D", "D#", "Eb", "E", "F",
    "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B",
]
# Scales supported by Strudel (https://strudel.cc/learn/mini-notation/#scale)
_SCALE_MODES: list[str] = [
    "major", "minor", "dorian", "phrygian", "lydian",
    "mixolydian", "locrian", "melodic minor", "harmonic minor",
    "pentatonic major", "pentatonic minor",
    "whole tone", "diminished", "augmented",
]

# Matches .scale("Root:mode") or .scale('Root:mode')
_SCALE_RE = re.compile(r'\.scale\((["\'])([A-Za-z#b]+):([^"\']*)\1\)', re.IGNORECASE)


def change_scale(buffer: str) -> tuple[str, str]:
    """Replace one .scale("Root:mode") call with a different root and/or mode.

    Returns (new_buffer, intent_description).
    """
    matches = list(_SCALE_RE.finditer(buffer))
    if not matches:
        log.debug("[change_scale] no .scale() call found in buffer")
        return buffer, "no scale found"

    match = random.choice(matches)
    quote = match.group(1)
    current_root = match.group(2).lower()
    current_mode = match.group(3).strip().lower()
    owner = _owning_function(buffer, match.start())

    new_root = random.choice([r for r in _SCALE_ROOTS if r.lower() != current_root])
    new_mode = random.choice([m for m in _SCALE_MODES if m.lower() != current_mode])
    new_call = f".scale({quote}{new_root}:{new_mode}{quote})"
    new_buffer = buffer[:match.start()] + new_call + buffer[match.end():]
    log.debug(
        "[change_scale] editing function '%s' — scale %s:%s → %s:%s",
        owner, current_root, current_mode, new_root, new_mode,
    )
    return new_buffer, f"scale {current_root}:{current_mode} → {new_root}:{new_mode}"


# ── BPM change ─────────────────────────────────────────────────────────────────

def change_bpm(buffer: str) -> tuple[str, str]:
    """Adjust or introduce a setcps() / setcpm() call.

    - setcpm() present: adjust ±15–30 % (clamped 30–240 BPM).
    - setcps() present: adjust ±15–30 % (clamped 0.3–3.0).
    - Neither present:  introduce setcps(1.0) at the top of the buffer.

    Returns (new_buffer, intent_description).
    """
    cpm_match = re.search(r'setcpm\(([0-9.]+)\)', buffer, re.IGNORECASE)
    cps_match = re.search(r'setcps\(([0-9.]+)\)', buffer, re.IGNORECASE)

    if cpm_match:
        current = float(cpm_match.group(1))
        factor = random.uniform(0.70, 1.30)
        new_val = round(max(30.0, min(240.0, current * factor)), 1)
        new_buffer = re.sub(r'setcpm\([0-9.]+\)', f'setcpm({new_val})', buffer, flags=re.IGNORECASE)
        log.debug("[change_bpm] setcpm matched: %s → %s (factor %.3f)", current, new_val, factor)
        return new_buffer, f"setcpm {current} → {new_val}"

    if cps_match:
        current = float(cps_match.group(1))
        factor = random.uniform(0.70, 1.30)
        new_val = round(max(0.3, min(3.0, current * factor)), 2)
        new_buffer = re.sub(r'setcps\([0-9.]+\)', f'setcps({new_val})', buffer, flags=re.IGNORECASE)
        log.debug("[change_bpm] setcps matched: %s → %s (factor %.3f)", current, new_val, factor)
        return new_buffer, f"setcps {current} → {new_val}"

    # Neither found: inject baseline
    log.debug("[change_bpm] no setcps/setcpm found — injecting setcps(1.0)")
    return f"setcps(1.0);\n{buffer}", "introduced setcps(1.0)"


# ── Main engine ───────────────────────────────────────────────────────────────

class RulesBasedChaosEngine:
    """Stateless rule-based chaos engine.

    On each call to :meth:`tick` it applies exactly **2** of the 3 available
    operation families to the supplied buffer, chosen at random each call:

    * ``pattern_mutation``  – one mini-notation transform on a pattern string
    * ``effects_change``    – add or remove chainable effects on a call
    * ``bpm_change``        – nudge or introduce a setcps()/setcpm() call

    Args:
        sounds:            Flat list of sound/drum names (e.g. from
                           the ``strudel://sounds`` resource).
        effects_knowledge: Full ``effects.json`` dict (with a ``"categories"``
                           key and per-effect ``"range"``/``"values"`` data)
                           *or* a flat list of effect dicts.  When omitted a
                           curated fallback set is used.
    """

    # Maps op name → relative pick weight.
    # bank_change and scale_change fire occasionally; bpm_change rarely.
    _OPS: dict[str, int] = {
        "pattern_mutation": 40,
        "effects_change":   40,
        "bank_change":      10,
        "scale_change":     10,
        "bpm_change":        5,
    }

    def __init__(
        self,
        sounds: list[str] | None = None,
        effects_knowledge: list | dict | None = None,
    ) -> None:
        self.sounds: list[str] = sounds or []
        self.effects_knowledge: list | dict = effects_knowledge or {}

    def tick(self, buffer: str) -> tuple[str, str]:
        """Apply randomly chosen operations.

        Returns:
            (mutated_buffer, intent_string)
        """
        ops = random.choices(list(self._OPS), weights=list(self._OPS.values()), k=1)
        log.debug("[tick] chosen ops: %s", ops)

        # Inventory every named function in the buffer before mutating
        func_inventory = _parse_function_names(buffer)
        log.debug(
            "[tick] buffer has %d named function(s): %s",
            len(func_inventory),
            [name for name, _ in func_inventory] or ["<none>"],
        )
        log.debug("[tick] input buffer:\n%s", buffer)

        result = buffer
        intents: list[str] = []
        for op in ops:
            if op == "pattern_mutation":
                result, intent = mutate_pattern(result, self.sounds)
            elif op == "effects_change":
                result, intent = change_effects(result, self.effects_knowledge)
            elif op == "bank_change":
                result, intent = change_bank(result)
            elif op == "scale_change":
                result, intent = change_scale(result)
            elif op == "bpm_change":
                result, intent = change_bpm(result)
            else:
                intent = ""
            log.debug("[tick] op=%s  intent=%r", op, intent)
            if intent:
                intents.append(intent)

        final_intent = "; ".join(intents) or "no change"
        log.debug("[tick] output buffer:\n%s", result)
        log.debug("[tick] final intent: %s", final_intent)
        return result, final_intent
