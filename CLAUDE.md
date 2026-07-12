# host-llm-on-gpu-server

Project for deploying and serving LLMs on rented GPU servers.

## Goal

Rent a GPU server on **vast.ai** via its API, run **Ollama** to host a language
model (e.g. `qwen2.5-coder`), and expose a port so a local machine can connect
to the Ollama API remotely.

- The model name is **config-driven** — set in `config.json` (e.g. `qwen2.5-coder`).
- Provider is **vast.ai** (fixed for now — not building a provider abstraction).
- Flow: `config.json` → vast.ai API rents server → onstart installs/runs Ollama +
  pulls the model → open port → local client connects to `http://<host>:<port>`.

### config.json (target shape)
```jsonc
{
  "vast": { "gpu": "RTX 4090", "max_price": 0.5, "disk_gb": 40 },
  "model": "qwen2.5-coder",
  "ollama_port": 11434
}
```
Do NOT commit real API keys — read the vast.ai key from an env var / `.env`.

## Cost guardrail
Rented GPUs bill by the hour. Always provide and document a teardown/destroy
path so an instance is never left running by accident.

## Roles (subagents)

Three specialized subagents live in `.claude/agents/`. Delegate to them with the Agent tool.

| Role | File | Owns | Never does |
|------|------|------|------------|
| **manager** | `.claude/agents/manager.md` | GitHub issues/PRs, task breakdown, coordination | Write product code |
| **coder** | `.claude/agents/coder.md` | Implement features/fixes, tests, branches | Merge/push without ask |
| **reviewer** | `.claude/agents/reviewer.md` | Review diffs & PRs (read-only) | Edit source files |

## Workflow

1. **manager** turns a request into a task block (context, files, acceptance, reviewer focus) and opens a GitHub issue.
2. **coder** implements on a feature branch, runs tests, and writes a changelog note.
3. **reviewer** checks the diff for correctness/security/simplicity and gives approve / request-changes.
4. **manager** opens the PR and (on explicit confirmation) merges.

## Guardrails
- Irreversible GitHub actions (merge, close, delete, force-push) require explicit user confirmation.
- Coder stays within task scope; unrelated issues go back to the manager.
- Reviewer is read-only.
