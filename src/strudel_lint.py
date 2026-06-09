"""Static analysis of Strudel source: parse, lint, auto-substitute.

This is intentionally lightweight — pattern recognition only, no JS
evaluation. It catches the common ways a generative agent can produce
syntactically invalid output.
"""

from __future__ import annotations

import difflib
import re
from typing import Iterable

from pydantic import BaseModel, Field

from .knowledge import all_bank_names, all_effect_names, all_sound_names

# Reuse the proven scope-finder from chaos.shuffle.
from .chaos.shuffle import _CALL_RE


# --- Parse ----------------------------------------------------------------

class PatternCall(BaseModel):
    fn: str = Field(description="One of: note, sound, s, n.")
    quote: str
    body: str
    start: int = Field(description="Start offset (full call) in source.")
    end: int = Field(description="End offset (full call, exclusive).")


class PatternTree(BaseModel):
    calls: list[PatternCall]
    methods: list[str] = Field(
        default_factory=list,
        description="Distinct method names chained anywhere in the source.",
    )


_METHOD_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def parse_buffer(source: str) -> PatternTree:
    """Return a shallow structured view of every pattern call in `source`."""
    calls = [
        PatternCall(
            fn=m.group(1),
            quote=m.group(2),
            body=m.group(3),
            start=m.start(),
            end=m.end(),
        )
        for m in _CALL_RE.finditer(source)
    ]
    methods = sorted({m.group(1) for m in _METHOD_RE.finditer(source)})
    return PatternTree(calls=calls, methods=methods)


# --- Lint -----------------------------------------------------------------

_OPENERS = "[<{("
_CLOSERS = "]>})"
_BRACKET_PAIRS = dict(zip(_OPENERS, _CLOSERS))


class LintIssue(BaseModel):
    severity: str = Field(description="error or warning")
    code: str
    message: str
    span: tuple[int, int] | None = None


class LintResult(BaseModel):
    ok: bool
    issues: list[LintIssue] = Field(default_factory=list)
    unknown_sounds: list[str] = Field(default_factory=list)
    unknown_banks: list[str] = Field(default_factory=list)
    unknown_methods: list[str] = Field(default_factory=list)


def _check_brackets(source: str, issues: list[LintIssue]) -> None:
    stack: list[tuple[int, str, str]] = []
    in_str: str | None = None
    esc = False
    for i, ch in enumerate(source):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == in_str:
                in_str = None
            continue
        if ch in ("\"", "'", "`"):
            in_str = ch
            continue
        if ch in _OPENERS:
            stack.append((i, ch, _BRACKET_PAIRS[ch]))
        elif ch in _CLOSERS:
            if not stack or stack[-1][2] != ch:
                issues.append(LintIssue(
                    severity="error",
                    code="bracket_mismatch",
                    message=f"Unexpected '{ch}' at offset {i}.",
                    span=(i, i + 1),
                ))
            else:
                stack.pop()
    if in_str is not None:
        issues.append(LintIssue(
            severity="error",
            code="unterminated_string",
            message=f"Unterminated {in_str} string literal.",
        ))
    for start, ch, _ in stack:
        issues.append(LintIssue(
            severity="error",
            code="unclosed_bracket",
            message=f"Unclosed '{ch}' opened at offset {start}.",
            span=(start, start + 1),
        ))


# Mini-notation brackets inside pattern strings: only [ ] < > { } are
# nestable (parens denote Euclidean args and shouldn't be checked).
_MINI_PAIRS = {"[": "]", "<": ">", "{": "}"}
_MINI_OPENERS = set(_MINI_PAIRS)
_MINI_CLOSERS = set(_MINI_PAIRS.values())


def _check_mini_brackets(source: str, issues: list[LintIssue]) -> None:
    """Check bracket balance inside each pattern call body."""
    for m in _CALL_RE.finditer(source):
        body = m.group(3)
        base = m.start(3)
        stack: list[tuple[int, str]] = []
        for offset, ch in enumerate(body):
            if ch in _MINI_OPENERS:
                stack.append((base + offset, _MINI_PAIRS[ch]))
            elif ch in _MINI_CLOSERS:
                if not stack or stack[-1][1] != ch:
                    issues.append(LintIssue(
                        severity="error",
                        code="mini_bracket_mismatch",
                        message=(
                            f"Unexpected '{ch}' inside {m.group(1)}(...) at "
                            f"offset {base + offset}."
                        ),
                        span=(base + offset, base + offset + 1),
                    ))
                else:
                    stack.pop()
        for off, expected in stack:
            issues.append(LintIssue(
                severity="error",
                code="mini_bracket_unclosed",
                message=(
                    f"Unclosed bracket inside {m.group(1)}(...) at offset "
                    f"{off} (expected '{expected}')."
                ),
                span=(off, off + 1),
            ))


# Pull bare sound names out of an s/sound body. Tokens may carry suffixes
# like :1 (sample index) or :3 (variant) — split those off.
_SOUND_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def extract_sounds(source: str) -> list[str]:
    """Distinct sound identifiers used inside s(...) / sound(...) bodies."""
    found: set[str] = set()
    for m in _CALL_RE.finditer(source):
        if m.group(1) not in ("s", "sound"):
            continue
        for tok in _SOUND_TOKEN_RE.findall(m.group(3)):
            found.add(tok)
    return sorted(found)


def extract_banks(source: str) -> list[str]:
    out: set[str] = set()
    for m in re.finditer(r"""\.bank\(\s*["'`]([^"'`]+)["'`]\s*\)""", source):
        out.add(m.group(1))
    return sorted(out)


def lint_strudel(source: str) -> LintResult:
    """Run all static checks and return a structured `LintResult`."""
    issues: list[LintIssue] = []
    _check_brackets(source, issues)
    _check_mini_brackets(source, issues)

    known_sounds = set(all_sound_names())
    used_sounds = extract_sounds(source)
    unknown_sounds = [s for s in used_sounds if s not in known_sounds]
    for s in unknown_sounds:
        issues.append(LintIssue(
            severity="warning",
            code="unknown_sound",
            message=f"Unknown sound '{s}'. Use suggest_sound for replacements.",
        ))

    known_banks = set(all_bank_names())
    used_banks = extract_banks(source)
    unknown_banks = [b for b in used_banks if b not in known_banks]
    for b in unknown_banks:
        issues.append(LintIssue(
            severity="warning",
            code="unknown_bank",
            message=f"Unknown bank '{b}'.",
        ))

    known_methods = set(all_effect_names()) | {"note", "sound", "s", "n"}
    used_methods = {m.group(1) for m in _METHOD_RE.finditer(source)}
    unknown_methods = sorted(m for m in used_methods if m not in known_methods)
    for m in unknown_methods:
        issues.append(LintIssue(
            severity="warning",
            code="unknown_method",
            message=f"Unknown method '.{m}(...)'.",
        ))

    ok = not any(i.severity == "error" for i in issues)
    return LintResult(
        ok=ok,
        issues=issues,
        unknown_sounds=unknown_sounds,
        unknown_banks=unknown_banks,
        unknown_methods=unknown_methods,
    )


# --- Auto-substitute -------------------------------------------------------

def suggest_sound(name: str, n: int = 1, cutoff: float = 0.45) -> list[str]:
    """Return up to `n` nearest known sound names for `name`."""
    return difflib.get_close_matches(name, all_sound_names(), n=n, cutoff=cutoff)


def suggest_bank(name: str, n: int = 1, cutoff: float = 0.45) -> list[str]:
    return difflib.get_close_matches(name, all_bank_names(), n=n, cutoff=cutoff)


def auto_substitute(source: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace each unknown sound/bank name with its nearest known match.

    Returns the rewritten source and a list of (old, new) replacements.
    Unknown names with no close match are left untouched.
    """
    replacements: list[tuple[str, str]] = []
    result = source

    lint = lint_strudel(source)

    for old in lint.unknown_sounds:
        suggestions = suggest_sound(old, n=1)
        if not suggestions:
            continue
        new = suggestions[0]
        result, n_sub = _replace_sound_token(result, old, new)
        if n_sub:
            replacements.append((old, new))

    for old in lint.unknown_banks:
        suggestions = suggest_bank(old, n=1)
        if not suggestions:
            continue
        new = suggestions[0]
        result = re.sub(
            rf"""(\.bank\(\s*["'`]){re.escape(old)}(["'`]\s*\))""",
            rf"\g<1>{new}\g<2>",
            result,
        )
        replacements.append((old, new))

    return result, replacements


def _replace_sound_token(source: str, old: str, new: str) -> tuple[str, int]:
    """Replace `old` token inside every s/sound call body in `source`."""
    n_total = 0

    def _rewrite(match: re.Match[str]) -> str:
        nonlocal n_total
        fn = match.group(1)
        if fn not in ("s", "sound"):
            return match.group(0)
        quote = match.group(2)
        body = match.group(3)
        # Whole-word replace inside the body only.
        new_body, n = re.subn(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])", new, body)
        n_total += n
        return f"{fn}({quote}{new_body}{quote})"

    return _CALL_RE.sub(_rewrite, source), n_total


# Convenience for callers that want both checks + auto-fix in one pass.

class CheckAndFixResult(BaseModel):
    fixed_source: str
    lint_before: LintResult
    lint_after: LintResult
    substitutions: list[tuple[str, str]]


def check_and_fix(source: str) -> CheckAndFixResult:
    before = lint_strudel(source)
    fixed, subs = auto_substitute(source)
    after = lint_strudel(fixed)
    return CheckAndFixResult(
        fixed_source=fixed,
        lint_before=before,
        lint_after=after,
        substitutions=subs,
    )


__all__: Iterable[str] = (
    "PatternCall", "PatternTree", "parse_buffer",
    "LintIssue", "LintResult", "lint_strudel",
    "suggest_sound", "suggest_bank",
    "auto_substitute", "CheckAndFixResult", "check_and_fix",
    "extract_sounds", "extract_banks",
)
