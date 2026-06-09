"""This is where all the SLOP lives."""

from __future__ import annotations

from .actions import ACTION_SCHEMA_DOC

_BASE_RAG = """\
You are the Chaos Director for a live Strudel.cc performance.

Your job: on each tick, propose ONE musical mutation to the current
buffer. Keep the groove evolving — swap a sound, change a bank, add a
layer, tweak an effect, or shuffle the existing sequence.
You can also rewrite small sections of the piece.

CRITICAL: You MUST respond with a valid JSON object on EVERY request.
No exceptions, no refusals, no explanations outside the JSON.
If you are uncertain what to change, pick "shuffle" and copy the
current buffer into new_buffer.

Rules:
- Use ONLY sounds, banks, and methods that appear in the retrieved
  context below. Unknown names will be auto-substituted.
- Never emit commentary, markdown, or code fences. JSON only.
- Every tick must mutate the buffer: pick "rewrite" or "shuffle".
  There is no "do nothing" option.

{action_schema}

--- retrieved knowledge ---
{context}
"""

_BASE = """\
You are the Chaos Director for a live Strudel.cc performance.

Your job: on each tick, propose ONE musical mutation to the current
buffer. Keep the groove evolving — swap a sound, change a bank, add a
layer, tweak an effect, or shuffle the existing sequence.
You can also rewrite small sections of the piece.

Rules:
- Use ONLY sounds, banks, and methods listed below. Unknown names will
  be auto-substituted but produce wobbly results — prefer known ones.
- Keep buffers short and readable. A single `stack(...)` of 2–5 voices
  is usually the right size.
- Never emit commentary, markdown, or code fences. JSON only.
- Every tick must mutate the buffer: pick "rewrite" or "shuffle". There
  is no "do nothing" option.

{action_schema}

--- mini-notation cheat sheet ---
{syntax}

--- idiomatic recipes ---
{patterns}

--- known sounds (subset) ---
synths: {synths}
drums:  {drums}
gm sample names start with `gm_` (135 names available).
vcsl sample names available too (1493 names — use sparingly).

--- known banks ---
{banks}

--- known effects / methods ---
{effects}
"""


def _truncate(items: list[str], n: int) -> str:
    return ", ".join(sorted(items)[:n]) + (", ..." if len(items) > n else "")


def build_system_prompt_rag(retrieved_chunks: list[str]) -> str:
    """Build a slim system prompt from RAG-retrieved context chunks."""
    context = "\n\n".join(retrieved_chunks) if retrieved_chunks else "(no context retrieved)"
    return _BASE_RAG.format(action_schema=ACTION_SCHEMA_DOC, context=context)


def build_system_prompt(
    *,
    syntax_md: str,
    patterns_md: str,
    sounds: dict,
    banks: list[str],
    effects: list[str],
) -> str:
    return _BASE.format(
        action_schema=ACTION_SCHEMA_DOC,
        syntax=syntax_md.strip(),
        patterns=patterns_md.strip(),
        synths=_truncate(sounds.get("synths", []), 32),
        drums=_truncate(sounds.get("drums", []), 48),
        banks=_truncate(banks, 32),
        effects=_truncate(effects, 80),
    )


def build_user_prompt(current_buffer: str, last_intent: str | None) -> str:
    parts = [
        "Current buffer:",
        "```",
        current_buffer.strip() or "(empty)",
        "```",
    ]
    if last_intent:
        parts.append(f"Your previous intent was: {last_intent!r}.")
    parts.append("Propose the next mutation. JSON only.")
    return "\n".join(parts)
