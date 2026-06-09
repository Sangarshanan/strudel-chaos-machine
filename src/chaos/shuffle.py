"""Shuffle-based chaos for Strudel `note|sound|s|n("…")` sequences.

The only public entrypoint is `chaos_shuffle_one`. It scans a source
string, finds every shuffleable scope (a quoted body, or any `[…]`,
`<…>`, `{…}` group inside one), and jumbles the top-level
whitespace-separated tokens of one randomly chosen scope.
"""

from __future__ import annotations

import random
import re

# Word-boundary on the left avoids matching the `s` in `cps`, `xs`, etc.
# Quote may be ", ', or `. Body must not cross a newline or contain the
# same quote char.
_CALL_RE = re.compile(
    r"""(?<![A-Za-z0-9_])(note|sound|s|n)\(\s*(["'`])([^"'`\n]*?)\2\s*\)""",
)

_OPENERS = "[<{"
_CLOSERS = "]>}"
_PAIRS = dict(zip(_OPENERS, _CLOSERS))


def _split_top_level(seq: str) -> list[str]:
    """Split a Strudel sequence on whitespace, respecting bracket nesting."""
    tokens: list[str] = []
    buf: list[str] = []
    stack: list[str] = []
    for ch in seq:
        if ch.isspace() and not stack:
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
        if ch in _OPENERS:
            stack.append(_PAIRS[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
        buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def _bracket_interiors(body: str, base: int) -> list[tuple[int, int]]:
    """Absolute (start, end) offsets of each bracket group's interior in body."""
    spans: list[tuple[int, int]] = []
    stack: list[tuple[int, str]] = []
    for i, ch in enumerate(body):
        if ch in _OPENERS:
            stack.append((i, _PAIRS[ch]))
        elif stack and ch == stack[-1][1]:
            open_idx, _ = stack.pop()
            spans.append((base + open_idx + 1, base + i))
    return spans


def chaos_shuffle_one(source: str, rng: random.Random) -> tuple[str, str | None]:
    """Pick one eligible shuffle scope and jumble its top-level tokens.

    Eligible scopes are: the body of any note/sound/s/n("…") call, plus
    every [...] / <...> / {...} group nested inside such a body. A scope
    is shuffleable if it splits into >= 2 top-level tokens.

    Returns (new_source, description). description is None if nothing
    eligible was found.
    """
    candidates: list[tuple[int, int, list[str]]] = []
    for m in _CALL_RE.finditer(source):
        body = m.group(3)
        body_start = m.start(3)
        scopes: list[tuple[int, int]] = [(body_start, body_start + len(body))]
        scopes.extend(_bracket_interiors(body, body_start))
        for start, end in scopes:
            interior = source[start:end]
            if " " not in interior and "\t" not in interior:
                continue
            tokens = _split_top_level(interior)
            if len(tokens) < 2:
                continue
            candidates.append((start, end, tokens))

    if not candidates:
        return source, None

    start, end, tokens = rng.choice(candidates)
    shuffled = list(tokens)
    rng.shuffle(shuffled)
    new_interior = " ".join(shuffled)
    old_interior = source[start:end]
    new_source = source[:start] + new_interior + source[end:]
    desc = f"'{old_interior}' -> '{new_interior}'"
    return new_source, desc
