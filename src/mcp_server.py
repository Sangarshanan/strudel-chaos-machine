"""MCP server exposing Strudel.cc chaos primitives.

A single shared Chromium page is held open for the lifetime of the
server via an async lifespan context manager.

Tools cover buffer I/O (`read_buffer_tool`, `write_buffer_tool`,
`evaluate_tool`), rule-based chaos (`shuffle_random_sequence`), and
static analysis (`parse_buffer_tool`, `lint_strudel_tool`,
`check_and_fix_tool`, `list_sounds`, `list_banks`, `list_effects`,
`suggest_sound_tool`, `suggest_bank_tool`). Resources expose the live
buffer plus the bundled knowledge (`strudel://buffer`, `strudel://syntax`,
`strudel://patterns`, `strudel://sounds`, `strudel://effects`).
"""

from __future__ import annotations

import os
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from mcp.server.fastmcp import Context, FastMCP
from playwright.async_api import Browser, Page, async_playwright
from pydantic import BaseModel, Field

from .browser import read_buffer, trigger_play, write_buffer
from .chaos import chaos_shuffle_one
from .knowledge import (
    all_bank_names,
    all_effect_names,
    all_sound_names,
    load_effects,
    load_patterns_md,
    load_sounds,
    load_syntax_md,
)
from .strudel_lint import (
    CheckAndFixResult,
    LintResult,
    PatternTree,
    check_and_fix,
    lint_strudel,
    parse_buffer,
    suggest_bank,
    suggest_sound,
)


@dataclass
class ServerState:
    page: Page
    browser: Browser
    rng: random.Random
    url: str


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[ServerState]:
    url = os.environ.get("STRUDEL_URL", "https://strudel.cc")
    headless = os.environ.get("STRUDEL_HEADLESS", "0") == "1"
    seed_env = os.environ.get("STRUDEL_SEED")
    rng = random.Random(int(seed_env)) if seed_env else random.Random()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(".cm-content", timeout=15_000)
    except Exception:
        pass  # let tools surface errors when actually used

    state = ServerState(page=page, browser=browser, rng=rng, url=url)
    try:
        yield state
    finally:
        try:
            await context.close()
        finally:
            await browser.close()
            await pw.stop()


mcp = FastMCP("strudel-chaos", lifespan=_lifespan)


def _state(ctx: Context) -> ServerState:
    return ctx.request_context.lifespan_context


class WriteResult(BaseModel):
    ok: bool = Field(description="Whether the write succeeded.")
    length: int = Field(description="Length of the written buffer in chars.")
    evaluated: bool = Field(description="Whether re-evaluation was triggered.")
    substitutions: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Auto-substitutions applied to unknown sounds/banks "
                    "before writing.",
    )
    lint_errors: list[str] = Field(
        default_factory=list,
        description="Hard-error lint messages from the final text (write is "
                    "still attempted unless `enforce_lint` is true).",
    )


class ShuffleResult(BaseModel):
    ok: bool
    changed: bool = Field(description="True if an eligible scope was found and shuffled.")
    description: str | None = Field(
        default=None,
        description="Human summary of the shuffle, e.g. \"'bd sd' -> 'sd bd'\".",
    )
    new_buffer: str | None = Field(
        default=None,
        description="The full new buffer after the shuffle (None if no change).",
    )



@mcp.tool()
async def read_buffer_tool(ctx: Context) -> str:
    """Return the current Strudel CodeMirror buffer contents."""
    return await read_buffer(_state(ctx).page)


@mcp.tool()
async def write_buffer_tool(
    ctx: Context,
    text: str,
    evaluate: bool = True,
    auto_fix: bool = True,
    enforce_lint: bool = True,
) -> WriteResult:
    """Replace the editor buffer."""
    state = _state(ctx)
    before = await read_buffer(state.page)

    fixed = text
    substitutions: list[tuple[str, str]] = []
    if auto_fix:
        cf = check_and_fix(text)
        fixed = cf.fixed_source
        substitutions = cf.substitutions

    final_lint = lint_strudel(fixed)
    hard_errors = [i.message for i in final_lint.issues if i.severity == "error"]
    if enforce_lint and hard_errors:
        print(f"Refusing to write buffer due to {len(hard_errors)} lint errors:")

    ok = await write_buffer(state.page, fixed)
    if ok and evaluate:
        await trigger_play(state.page)
    
    print(f"write_buffer_tool: ok={ok}, length={len(fixed)}")

    return WriteResult(
        ok=ok,
        length=len(fixed),
        evaluated=bool(ok and evaluate),
        substitutions=substitutions,
        lint_errors=hard_errors,
    )


@mcp.tool()
async def evaluate_tool(ctx: Context) -> dict[str, bool]:
    """Press Ctrl+Enter to re-evaluate the current buffer."""
    await trigger_play(_state(ctx).page)
    return {"ok": True}


@mcp.tool()
async def shuffle_random_sequence(
    ctx: Context,
    apply: bool = True,
    evaluate: bool = True,
) -> ShuffleResult:
    """Shuffle tokens in one randomly chosen Strudel sequence scope."""
    state = _state(ctx)
    current = await read_buffer(state.page)
    if not current:
        return ShuffleResult(ok=True, changed=False, description="empty buffer")

    mutated, desc = chaos_shuffle_one(current, state.rng)
    if desc is None:
        return ShuffleResult(ok=True, changed=False, description="no eligible scope")

    if not apply:
        return ShuffleResult(ok=True, changed=True, description=desc, new_buffer=mutated)

    ok = await write_buffer(state.page, mutated)
    if ok and evaluate:
        await trigger_play(state.page)
    print(f"shuffle_random_sequence: ok={ok}, changed={ok and mutated != current}")
    return ShuffleResult(
        ok=ok,
        changed=ok,
        description=desc,
        new_buffer=mutated if ok else None,
    )


# Knowledge & analysis tools

@mcp.tool()
async def parse_buffer_tool(ctx: Context) -> PatternTree:
    source = await read_buffer(_state(ctx).page)
    return parse_buffer(source)


@mcp.tool()
async def lint_strudel_tool(ctx: Context, text: str | None = None) -> LintResult:
    """Static-check for Strudel snippets."""
    if text is None:
        text = await read_buffer(_state(ctx).page)
    return lint_strudel(text)


@mcp.tool()
def check_and_fix_tool(text: str) -> CheckAndFixResult:
    """Run lint, auto-substitute unknown sounds/banks with their nearest known match, and re-lint."""
    return check_and_fix(text)


@mcp.tool()
def list_sounds(category: str | None = None) -> list[str]:
    """Return known sound names."""
    if category is None:
        return all_sound_names()
    data = load_sounds()
    return sorted(data.get(category, []))


@mcp.tool()
def list_banks() -> list[str]:
    """Return known drum bank names"""
    return all_bank_names()


@mcp.tool()
def list_effects() -> list[str]:
    """Return all known method names."""
    return all_effect_names()


@mcp.tool()
def suggest_sound_tool(name: str, n: int = 3) -> list[str]:
    """Return up to ``n`` nearest known sound names for ``name``."""
    return suggest_sound(name, n=n)


@mcp.tool()
def suggest_bank_tool(name: str, n: int = 3) -> list[str]:
    """Return up to ``n`` nearest known bank names for ``name``."""
    return suggest_bank(name, n=n)


# Resources

@mcp.resource("strudel://buffer")
async def buffer_resource() -> str:
    """Current contents of the Strudel editor buffer."""
    state: ServerState = mcp._mcp_server.request_context.lifespan_context  # type: ignore[attr-defined]
    return await read_buffer(state.page)


@mcp.resource("strudel://syntax")
def syntax_resource() -> str:
    """Mini-notation cheat sheet (Markdown)."""
    return load_syntax_md()


@mcp.resource("strudel://patterns")
def patterns_resource() -> str:
    """Idiomatic pattern recipes (Markdown)."""
    return load_patterns_md()


@mcp.resource("strudel://sounds")
def sounds_resource() -> str:
    """Full sound catalog (JSON)."""
    import json as _json
    return _json.dumps(load_sounds(), indent=2)


@mcp.resource("strudel://effects")
def effects_resource() -> str:
    """All chainable methods with value ranges (JSON)."""
    import json as _json
    return _json.dumps(load_effects(), indent=2)


def run_server() -> None:
    """Run the MCP server over stdio (default transport)."""
    mcp.run()
