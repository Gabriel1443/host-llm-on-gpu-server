# host-llm-on-gpu-server

Rent a GPU server on **[vast.ai](https://vast.ai)** via its API, run **Ollama** to
host a language model (e.g. `qwen2.5-coder`), and expose a port so your local
machine can connect to the remote Ollama API.

## How it works

```
config.json  ──►  vast.ai API rents a GPU server
                     └─► onstart: install & run Ollama, pull the model
                           └─► expose port ──► local connects to http://<host>:<port>
```

- The model is **config-driven** — set it in `config.json` (e.g. `qwen2.5-coder`).
- Provider is **vast.ai** (fixed for now — no provider abstraction).
- Rented GPUs **bill by the hour** — always destroy the instance when done.

## config.json

```jsonc
{
  "vast": {
    "gpu": "RTX 4090",
    "max_price": 0.5,
    "disk_gb": 40,
    "verified": true,     // optional, default true — only rent from vast.ai-verified hosts
    "min_cpu_cores": 2    // optional, no floor if omitted
  },
  "model": "qwen2.5-coder",
  "ollama_port": 11434
}
```

`vast.verified` filters to hosts vast.ai has verified (vs. individually-run
machines with no platform reliability guarantee). `vast.min_cpu_cores` sets a
floor on the *effective* (allocated) CPU cores for the instance — useful if a
too-thin CPU slice bottlenecks model download/decompression.

The vast.ai **API key is read from an environment variable / `.env`** — it is
never stored in `config.json` and never committed.

## Setup

This project uses **[uv](https://docs.astral.dev/uv/)** for Python.

```bash
uv sync                              # create .venv (Python >=3.11)
cp config.json.example config.json   # then edit
cp .env.example .env                 # then add your VAST_API_KEY
source .env                          # or export VAST_API_KEY=...
```

## Usage

### 1. Rent a server and start Ollama

```bash
uv run python provision.py
```

Searches vast.ai for an offer matching `config.json`, rents the cheapest
match, and boots it running `ollama serve` plus `ollama pull <model>`. Prints
the instance id and the `http://<host>:<port>` to connect to. The instance id
is also saved locally (`.vast_state.json`) so `teardown.py` doesn't need it
passed in manually.

The model may still be downloading when this command returns — larger models
take a while to pull.

### 2. Verify it's reachable

```bash
uv run python connect.py
```

Resolves the rented instance (from local state, or `--instance-id`) and
checks `GET /api/tags` (lists models) and `POST /api/generate` (asks the
model to respond). Re-run this if you provisioned recently and want to
confirm the model finished downloading.

### 3. Destroy the instance when done

```bash
uv run python teardown.py
```

**Do this every time you're done** — rented GPUs bill by the hour. Destroys
the instance tracked in local state (prompts for confirmation; pass `--yes`
to skip it, or `--instance-id` to target a different instance). Safe to run
with nothing to destroy.

### Running the tests

```bash
uv run python -m unittest discover -s tests
```

## Roles

Development uses three subagents (see [CLAUDE.md](CLAUDE.md)): **manager** (GitHub),
**coder**, and **reviewer**.
