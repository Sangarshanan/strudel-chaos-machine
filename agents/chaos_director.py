"""Chaos director: drives the strudel-chaos MCP server.

Two engines are available (select with ``--engine``):

``llm``   (default) – stateless loop powered by an Ollama LLM:
  1. Read live buffer + cached knowledge resources.
  2. Ask Ollama for ONE structured Action.
  3. Translate it into a single MCP tool call.
  4. Sleep until the next tick.

``rules`` – deterministic rule-based engine (no LLM required):
  On each tick chooses 2 of 3 operation families at random:
    • pattern_mutation  – apply a mini-notation trick (*, /, @, !, [], <>, etc.)
    • effects_change    – add or remove chainable effects
    • bpm_change        – nudge / introduce setcps() or setcpm()
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from pathlib import Path

from .actions import Action, ActionType
from .ollama_client import OllamaClient, TRANSPORT_FAILURE
from .prompts import build_system_prompt_rag, build_user_prompt
from .rag import KnowledgeIndex
from .mutations import enrich_buffer, extract_cps_from_buffer
from .rule_based_chaos import RulesBasedChaosEngine


# MCP stuff

@asynccontextmanager
async def _spawn_mcp_stdio(server_cmd: list[str]) -> AsyncIterator[ClientSession]:
    """Launch the MCP server as a subprocess over stdio and initialize a session."""
    params = StdioServerParameters(command=server_cmd[0], args=server_cmd[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _unwrap(sc: dict | None) -> object:
    if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
        return sc["result"]
    return sc


async def _read_text_resource(client: ClientSession, uri: str) -> str:
    res = await client.read_resource(uri)
    return "\n".join(getattr(c, "text", "") or "" for c in res.contents)


async def _read_json_resource(client: ClientSession, uri: str) -> dict | list:
    raw = await _read_text_resource(client, uri)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


async def _load_knowledge(client: ClientSession) -> tuple[str, str, dict, list[str], list[str]]:
    syntax = await _read_text_resource(client, "strudel://syntax")
    patterns = await _read_text_resource(client, "strudel://patterns")
    sounds = await _read_json_resource(client, "strudel://sounds")
    banks_res = await client.call_tool("list_banks", {})
    effects_res = await client.call_tool("list_effects", {})
    banks = _unwrap(banks_res.structuredContent or {}) or []
    effects = _unwrap(effects_res.structuredContent or {}) or []
    return (
        syntax,
        patterns,
        sounds if isinstance(sounds, dict) else {},
        list(banks) if isinstance(banks, list) else [],
        list(effects) if isinstance(effects, list) else [],
    )


# Rules-based tick

async def _tick_rules(
    *,
    client: ClientSession,
    engine: RulesBasedChaosEngine,
) -> str | None:
    """Run a single rules-based director tick. Returns the intent string (or None)."""
    read = await client.call_tool("read_buffer_tool", {})
    current = (read.content[0].text if read.content else "") or ""

    if not current.strip():
        print("[rules] empty buffer — skipping tick", file=sys.stderr)
        return None

    new_buffer, intent = engine.tick(current)
    print(f"[rules] {intent}")

    if new_buffer.strip() == current.strip():
        print("[rules]   -> no change produced", file=sys.stderr)
        return intent

    res = await client.call_tool(
        "write_buffer_tool",
        {"text": new_buffer, "evaluate": True, "auto_fix": True,
         "enforce_lint": True},
    )
    sc = res.structuredContent or {}
    if sc.get("ok"):
        subs = sc.get("substitutions") or []
        print(
            f"[rules]   -> wrote {sc.get('length', 0)} chars"
            f"{f', auto-fixed {len(subs)} tokens' if subs else ''}"
        )
    else:
        errs = sc.get("lint_errors") or [sc.get("error")]
        print(f"[rules]   -> REJECTED: {errs}", file=sys.stderr)
    return intent


# LLM Action dispatch

async def _apply_action(
    client: ClientSession,
    action: Action,
) -> dict:
    """Translate an Action into an MCP tool call. Returns a small status dict."""
    if action.type is ActionType.SHUFFLE:
        res = await client.call_tool(
            "shuffle_random_sequence", {"apply": True, "evaluate": True},
        )
        return {
            "ok": True,
            "kind": "shuffle",
            "result": res.structuredContent or {},
        }

    # rewrite
    if not action.new_buffer or not action.new_buffer.strip():
        return {"ok": False, "kind": "rewrite", "error": "missing new_buffer"}
    
    # Extract current CPS from the buffer to inform BPM changes
    current_cps = extract_cps_from_buffer(action.new_buffer)
    
    # Enrich the buffer with effects, BPM, and function prefixes
    enriched_buffer = enrich_buffer(
        action.new_buffer,
        add_prefix=True,
        add_effects=True,
        update_bpm=True,
        current_cps=current_cps,
        function_prefix="phrase",
    )
    
    res = await client.call_tool(
        "write_buffer_tool",
        {"text": enriched_buffer, "evaluate": True, "auto_fix": True,
         "enforce_lint": True},
    )
    sc = res.structuredContent or {}
    return {"ok": bool(sc.get("ok")), "kind": "rewrite", "result": sc}


# Main loop

async def _tick(
    *,
    client: ClientSession,
    ollama: OllamaClient,
    rag_index: KnowledgeIndex,
    last_intent: str | None,
) -> str | None:
    """Run a single director tick. Returns the new last_intent (or None)."""
    read = await client.call_tool("read_buffer_tool", {})
    current = (read.content[0].text if read.content else "") or ""

    # Retrieve only the knowledge chunks relevant to the current state.
    query = f"{current} {last_intent or ''}".strip()
    chunks = rag_index.query(query, n_results=6)
    system_prompt = build_system_prompt_rag(chunks)

    user = build_user_prompt(current, last_intent)
    action = await ollama.chat_schema(
        system=system_prompt, user=user, schema=Action,
    )
    if action is TRANSPORT_FAILURE:
        # Some Ollama error :(
        print("[director] transport failure — falling back to shuffle",
              file=sys.stderr)
        action = Action(type=ActionType.SHUFFLE, intent="fallback shuffle",
                        new_buffer=current)
    elif action is None:
        # skip this tick rather than silently playing bad output.
        print("[director] schema validation failed, skipping tick",
              file=sys.stderr)
        return last_intent

    print(f"[director] {action.type.value}: {action.intent}")
    status = await _apply_action(client, action)
    if status.get("ok"):
        kind = status.get("kind")
        if kind == "rewrite":
            res = status.get("result") or {}
            subs = res.get("substitutions") or []
            print(
                f"[director]   -> wrote {res.get('length', 0)} chars"
                f"{f', auto-fixed {len(subs)} tokens' if subs else ''}"
            )
        elif kind == "shuffle":
            res = status.get("result") or {}
            if res.get("changed"):
                print(f"[director]   -> {res.get('description')}")
            else:
                print(f"[director]   -> no eligible scope to shuffle")
    else:
        result = status.get("result") or {}
        errs = result.get("lint_errors") or [status.get("error")]
        print(
            f"[director]   -> REJECTED ({status.get('kind')}): {errs}",
            file=sys.stderr,
        )
    return action.intent


async def run_director(
    *,
    model: str | None = None,
    interval: float = 8.0,
    server_cmd: list[str] | None = None,
    ollama: OllamaClient | None = None,
    client: ClientSession | None = None,
    max_ticks: int | None = None,
    rag_dir: str | Path | None = Path(".chroma"),
    engine: str = "llm",
) -> None:
    """Run the director loop until cancelled.

    Args:
        engine: ``"llm"`` (default) – use the Ollama LLM on every tick.
                ``"rules"``         – use the deterministic rule-based engine
                                      (no LLM required; ``model`` is ignored).
    """
    if engine not in ("llm", "rules"):
        raise ValueError(f"engine must be 'llm' or 'rules', got {engine!r}")

    if server_cmd is None:
        server_cmd = [sys.executable, "-m", "src.app"]

    rag_index = KnowledgeIndex(persist_dir=rag_dir)

    owns_ollama = ollama is None
    if engine == "llm" and ollama is None:
        if model is None:
            raise ValueError("model is required when engine='llm' and ollama client is not provided")
        ollama = OllamaClient(model=model)

    async def _loop(session: ClientSession) -> None:
        syntax, patterns, sounds, banks, effects = await _load_knowledge(session)

        # Build the rules engine if requested (loads full effects JSON for ranges)
        rules_engine: RulesBasedChaosEngine | None = None
        if engine == "rules":
            effects_json = await _read_json_resource(session, "strudel://effects")
            all_sounds: list[str] = []
            if isinstance(sounds, dict):
                for v in sounds.values():
                    if isinstance(v, list):
                        all_sounds.extend(str(s) for s in v)
            rules_engine = RulesBasedChaosEngine(
                sounds=all_sounds,
                effects_knowledge=effects_json,
            )
            print(
                f"[director] rules engine ready "
                f"({len(all_sounds)} sounds loaded)",
                file=sys.stderr,
            )

        if engine == "llm":
            if not rag_index.is_built():
                n = rag_index.build(
                    syntax_md=syntax,
                    patterns_md=patterns,
                    sounds=sounds,
                    banks=banks,
                    effects=effects,
                )
                print(f"[director] built knowledge index: {n} chunks", file=sys.stderr)
            else:
                print(
                    f"[director] reusing knowledge index "
                    f"({rag_index._col.count()} chunks)",
                    file=sys.stderr,
                )

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass

        last_intent: str | None = None
        ticks = 0
        while not stop.is_set():
            if engine == "rules" and rules_engine is not None:
                last_intent = await _tick_rules(
                    client=session,
                    engine=rules_engine,
                )
            else:
                last_intent = await _tick(
                    client=session,
                    ollama=ollama,
                    rag_index=rag_index,
                    last_intent=last_intent,
                )
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    try:
        if client is not None:
            await _loop(client)
        else:
            async with _spawn_mcp_stdio(server_cmd) as session:
                await _loop(session)
    finally:
        if owns_ollama:
            await ollama.aclose()


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--engine",
        choices=("llm", "rules"),
        default=os.environ.get("CHAOS_ENGINE", "llm"),
        help="Chaos engine to use: 'llm' (default, requires Ollama) or "
             "'rules' (deterministic rule-based, no LLM needed). "
             "Can also be set via the CHAOS_ENGINE env var.",
    )
    ap.add_argument("--model", default=os.environ.get("OLLAMA_MODEL",
                                                       "qwen3.5:0.8b"))
    ap.add_argument("--interval", type=float, default=5.0,
                    help="Seconds between director ticks (default: 5).")
    ap.add_argument("--rag-dir", default=".chroma",
                    help="Directory for the ChromaDB knowledge index "
                         "(default: .chroma). Pass empty string for in-memory.")
    ap.add_argument("--server-cmd", nargs=argparse.REMAINDER,
                    help="Command to launch the MCP server (default: "
                         "`python -m src.app`). Pass after `--`.)")
    args = ap.parse_args()

    server_cmd = args.server_cmd or None
    rag_dir: str | None = args.rag_dir if args.rag_dir else None
    try:
        asyncio.run(run_director(
            model=args.model,
            interval=args.interval,
            server_cmd=server_cmd,
            rag_dir=rag_dir,
            engine=args.engine,
        ))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
