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
  "vast":  { "gpu": "RTX 4090", "max_price": 0.5, "disk_gb": 40 },
  "model": "qwen2.5-coder",
  "ollama_port": 11434
}
```

The vast.ai **API key is read from an environment variable / `.env`** — it is
never stored in `config.json` and never committed.

## Setup

This project uses **[uv](https://docs.astral.dev/uv/)** for Python.

```bash
uv sync                        # create .venv (Python >=3.11)
cp config.json.example config.json   # then edit
cp .env.example .env                 # then add your VAST_API_KEY
source .env                          # or export VAST_API_KEY=...

uv run python config.py        # sanity-check the config loads
uv run python -m unittest discover -s tests
```

## Usage

> Scripts are being built — see the [open issues](https://github.com/Gabriel1443/host-llm-on-gpu-server/issues).
> The intended workflow:

```bash
# 1. rent a GPU server matching config.json and start Ollama
#    (provisioning script)

# 2. connect from local
curl http://<host>:<port>/api/tags

# 3. destroy the instance to stop billing
#    (teardown script)
```

## Roles

Development uses three subagents (see [CLAUDE.md](CLAUDE.md)): **manager** (GitHub),
**coder**, and **reviewer**.
