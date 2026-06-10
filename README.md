# Strudel Chaos Machine

This project aims to create computational performance as a site of conflict rather than control. Challenging expectations that treat artificial intelligence as an obedient tool or cooperative collaborator, this performance introduces an adversarial agent that actively interferes with the act of live coding. As the performer live codes music, the AI agent simultaneously rewrites that code, injects competing logic, and destabilizes timing and structure. The resulting performance is not a harmonious co-creation, but a high-stakes negotiation and adapting to changes made in real time. By making the underlying code inherently unstable, this work interrogates the limits of human agency, the fragility of control, and the aesthetic potential of systemic friction.

The result is an MCP server that exposes [Strudel.cc](https://strudel.cc) as a surface to induce chaos. Tools read/write the code buffer, validate against a strudel sound catalog and trigger sound playback. Pair it with the bundled `agents.chaos_director` to let a local Ollama model drive the mutations on its own, resulting in (un)expected chaos that the user now needs to work with while performing.

## Run locally

**Install dependencies**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**Start chaos director**

```bash
# pull a model first if you haven't, use any model.
ollama pull <model_name>

python -m agents --model <model_name>
```

This opens a Chromium window pointing at `https://strudel.cc` and starts mutating the buffer on each tick.
