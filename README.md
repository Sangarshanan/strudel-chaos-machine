# Strudel Chaos Machine

An MCP server that holds a live [Strudel.cc](https://strudel.cc) browser tab open and exposes it as a tool surface. Tools read/write the CodeMirror buffer, lint code against a strudel sound catalog, auto-fix unknown tokens, and trigger playback. Pair it with the bundled `agents.chaos_director` to let a local Ollama model drive mutations on its own.

## Run locally

**1. Install dependencies**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**2. Start the chaos director**

```bash
# pull a model first if you haven't, use any model.
ollama pull gemma4:latest

python -m agents.chaos_director --model gemma4:latest
```

This opens a Chromium window pointing at `https://strudel.cc` and starts mutating the buffer on each tick.
