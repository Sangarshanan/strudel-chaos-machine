"""Action that chaos director may pick on each tick."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    REWRITE = "rewrite"  # propose a new full buffer
    SHUFFLE = "shuffle"  # delegate to shuffle_random_sequence


class Action(BaseModel):
    """A single mutation proposal returned by the LLM."""

    type: ActionType = Field(description="Which MCP tool to invoke.")
    intent: str = Field(
        description="One short sentence explaining the musical intent.",
        max_length=240,
    )
    new_buffer: str = Field(
        description=(
            "Full replacement Strudel program. REQUIRED for type == 'rewrite'. "
            "For type == 'shuffle', repeat the current buffer unchanged. "
            "Use only known sounds, banks, and methods. No markdown fences."
        ),
        max_length=600,
    )


# Short prose summary embedded in the system prompt as a hint
ACTION_SCHEMA_DOC = """\
Respond with ONE JSON object matching this shape:

  type:       "rewrite" | "shuffle"
  intent:     short sentence explaining the musical move
  new_buffer: full Strudel program (required when type == "rewrite",
              must be plain JS — no markdown fences)

New mutation features:
- Prefix functions with $name: for clarity (e.g., $drums: s("bd*4"))
- Add effects to individual functions: .gain(0.5).delay(0.3).lpf(1200)
- Modify BPM with setcps(value) where value ranges 0.5 to 2.0
  Example: setcps(1.5); s("bd*4")

Never copy the example intents verbatim — invent your own.

Examples (do NOT echo these strings — they are shape demos only):
  {"type":"shuffle","intent":"permute the hats while keeping the kick"}
  {"type":"rewrite","intent":"add reverb to drums and speed up",
   "new_buffer":"setcps(1.5);\\n$drums: stack(s(\\"bd*4\\").bank(\\"RolandTR909\\").room(0.5), s(\\"hh*7\\").gain(0.6).delay(0.3))"}
"""
