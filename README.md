# Strudel Chaos Machine

This project aims to create computational performance as a site of conflict rather than control. Challenging expectations that treat artificial intelligence as an obedient tool or cooperative collaborator, this performance introduces an adversarial agent that actively interferes with the act of live coding. As the performer live codes music, the AI agent simultaneously rewrites that code, injects competing logic, and destabilizes timing and structure. The resulting performance is not a harmonious co-creation, but a high-stakes negotiation and adapting to changes made in real time. By making the underlying code inherently unstable, this work interrogates the limits of human agency, the fragility of control, and the aesthetic potential of systemic friction.


[<video src="chaos.mp4" width="320" height="240" controls></video>
](https://github.com/user-attachments/assets/6cf91c53-381a-4299-b440-be045a1763bb
)

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
ollama pull gemma4:e2b-mlx-bf16 # use any model (obv)
python -m agents --model gemma4:e2b-mlx-bf16
```

Rule based agent

```bash
python -m agents --engine rules --interval 10
```


This opens a Chromium window pointing at `https://strudel.cc` and starts mutating the buffer on each tick.


## Performance Practice

Performing with an adversarial AI acts as a microcosm for our broader relationship with algorithmic systems. People increasingly rely on black-box algorithms that curate our media, manage our communications, and dictate our workflows. By making the algorithm explicitly adversarial and granting it direct write-access to the code buffer. The live coder is no longer an omnipotent author, but as a negotiator, continuously adapting to an environment much like the one that surrounds us.


