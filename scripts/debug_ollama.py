"""
Standalone debug script for OllamaClient.

Usage:
    python debug_ollama.py --model gemma4:e2b-mlx-bf16
"""

from __future__ import annotations

import asyncio
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from agents.ollama_client import OllamaClient, TRANSPORT_FAILURE
from agents.actions import Action
from agents.prompts import build_system_prompt_rag
from agents.rag import KnowledgeIndex
from agents.mutations import enrich_buffer, extract_cps_from_buffer


# Hello Ollama, are you there?

async def ping(model: str) -> None:
    print(f"\n[ping] sending raw chat to model={model!r} ...")
    from ollama import AsyncClient
    try:
        resp = await AsyncClient().chat(
            model=model,
            messages=[{"role": "user", "content": "Say the word PONG and nothing else."}],
        )
        print(f"[ping] response: {resp.message.content!r}")
        print(f"[ping] done_reason={getattr(resp, 'done_reason', '?')} "
              f"eval_count={getattr(resp, 'eval_count', '?')}")
    except Exception as e:
        print(f"[ping] FAILED: {e}", file=sys.stderr)
        sys.exit(1)


# Full chat_schema path with Action

SYSTEM = (
    "You are a Strudel.cc chaos director. "
    "Respond with ONE JSON object — no prose, no fences."
)
USER = (
    "Current buffer:\n```\ns(\"bd sd hh cp\").bank(\"tr909\")\n```\n"
    "Propose the next mutation. JSON only."
)


def _load_knowledge() -> tuple[str, str, dict, list[str], list[str]]:
    """Load syntax, patterns, sounds, banks, and effects from knowledge files."""
    knowledge_dir = Path("src/knowledge")
    
    with open(knowledge_dir / "syntax.md") as f:
        syntax = f.read()
    
    with open(knowledge_dir / "patterns.md") as f:
        patterns = f.read()
    
    with open(knowledge_dir / "sounds.json") as f:
        sounds_data = json.load(f)
    
    with open(knowledge_dir / "effects.json") as f:
        effects_data = json.load(f)
    
    sounds = {
        "synths": sounds_data.get("synths", []),
        "drums": sounds_data.get("drums", []),
    }
    banks = sounds_data.get("banks", [])
    effects = effects_data.get("effects", []) if isinstance(effects_data, dict) else effects_data
    
    return syntax, patterns, sounds, banks, effects


def _extract_bank_from_buffer(buffer: str) -> str | None:
    """Extract the sound bank name from a Strudel buffer.
    
    Looks for patterns like .bank("...") or .bank('...') 
    """
    import re
    match = re.search(r'\.bank\(["\']([^"\']+)["\']\)', buffer)
    return match.group(1) if match else None


async def schema_chat(model: str, buffer: str | None = None) -> None:
    if buffer is None:
        buffer = USER
    
    syntax, patterns, sounds, banks, effects = _load_knowledge()
    
    # Build RAG index and retrieve context
    rag_dir = Path(".chroma")
    rag_index = KnowledgeIndex(persist_dir=rag_dir)
    if not rag_index.is_built():
        n = rag_index.build(
            syntax_md=syntax,
            patterns_md=patterns,
            sounds=sounds,
            banks=banks,
            effects=effects,
        )
        print(f"[debug] built RAG index: {n} chunks", file=sys.stderr)
    
    # Query based on the actual bank in the buffer
    bank = _extract_bank_from_buffer(buffer)
    query_text = f"{bank} sounds drums bank" if bank else "sounds bank drums"
    chunks = rag_index.query(query_text, n_results=3)
    system = build_system_prompt_rag(chunks)
    print(f"[debug] extracted bank from buffer: {bank!r}", file=sys.stderr)
    print(f"[debug] RAG query: {query_text!r}", file=sys.stderr)
    
    print(f"\n[schema] testing chat_schema with model={model!r} ...", file=sys.stderr)
    print(f"[schema] system prompt length: {len(system)} chars", file=sys.stderr)
    
    client = OllamaClient(model=model, debug=True)
    result = await client.chat_schema(system=system, user=buffer, schema=Action)
    await client.aclose()

    print()
    if result is TRANSPORT_FAILURE:
        print("[schema] TRANSPORT_FAILURE — Ollama down or hit num_predict cap")
        sys.exit(1)
    elif result is None:
        print("[schema] None — JSON was valid but failed Pydantic schema validation")
        sys.exit(1)
    else:
        print(f"[schema] SUCCESS: {result!r}")
        print(f"         type        = {result.type.value}")
        print(f"         intent      = {result.intent!r}")
        print(f"         new_buffer  = {result.new_buffer!r}")
        
        # Show enrichment
        print("\n[enrichment] applying mutations...")
        current_cps = extract_cps_from_buffer(result.new_buffer)
        enriched = enrich_buffer(
            result.new_buffer,
            add_prefix=True,
            add_effects=True,
            update_bpm=True,
            current_cps=current_cps,
            function_prefix="phrase",
        )
        print(f"[enrichment] enriched_buffer =\n{enriched}")


# Schema shape check (aka vibe check)

def show_schema() -> None:
    schema = Action.model_json_schema()
    print("\n[schema shape] Action.model_json_schema():")
    print(json.dumps(schema, indent=2))


# Main

async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="gemma4:e2b-mlx-bf16",
                    help="Ollama model tag to test (default: gemma4:e2b-mlx-bf16)")
    ap.add_argument("--raw", action="store_true",
                    help="Run raw ping only (skip schema chat)")
    ap.add_argument("--schema-only", action="store_true",
                    help="Print the Action JSON schema and exit")
    args = ap.parse_args()

    if args.schema_only:
        show_schema()
        return

    show_schema()
    await ping(args.model)

    if not args.raw:
        await schema_chat(args.model)


if __name__ == "__main__":
    asyncio.run(main())
