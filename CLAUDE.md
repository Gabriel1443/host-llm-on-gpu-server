# host-llm-on-gpu-server

Project for deploying and serving LLMs on GPU servers.

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
