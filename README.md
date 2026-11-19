# copydesk

A vague ad brief in, three compliant Meta ads out. A small multi-agent pipeline in LangGraph with a
compliance gate and an eval harness. The brand, Acme Telehealth, is fictional.

Built in one take with Claude Code: the AI writes the code, I make the decisions.
**Video:** [video/copydesk-demo.mp4](video/copydesk-demo.mp4) (32 min, download to watch).

## How it works

```
brief ─► strategist ─► 3 angles ─┬─► copywriter ─► compliance ─┐
         (drops non-compliant    ├─► copywriter ─► compliance ─┼─► report.html
          asks)                  └─► copywriter ─► compliance ─┘
                                        ▲              │ fail: rewrite with the
                                        └──────────────┘ violations (max 2, then "flagged")
```

- **Strategist** turns the brief into three different angles and lists any asks it dropped for compliance.
- **Copywriters** run in parallel, one per angle (LangGraph `Send`, with a reducer on the shared output).
- **Compliance** runs deterministic checks from `rules.yaml` first, then an LLM review. A failing ad goes
  back to its copywriter with the violations, up to two times.
- **Why plain LangGraph, not an agent framework:** the fan-out and the rewrite limit are business rules,
  so they're fixed edges, not decisions left to the model.

## Run it

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and an Anthropic API key.

```bash
cp .env.example .env        # then set ANTHROPIC_API_KEY
uv sync
uv run python -m copydesk "spring push for our weight-loss program, busy parents, Meta"
```

It prints each ad's status, any dropped asks and token usage, and writes `out/report.html`.

## Tests and evals

```bash
uv run pytest -q                                          # rule checker + graph with fake agents
uv run python -m evals.run --save-baseline                # real model, 8 golden briefs
uv run python -m evals.run --compare results/baseline.json
```

The eval scores every case with the same checks as the pipeline (`copydesk.rules`) plus a separate LLM
judge with its own prompt. It also tracks rewrites and tokens. `--compare` exits 1 if any quality metric
drops or rewrites/tokens grow more than 30%: a prompt that still passes but needs twice the rewrites
is a regression too.

## Repo

- `src/copydesk/`: graph, agents (one per file), rules and report
- `evals/`: golden briefs, judge, runner
- `CLAUDE.md`, `.claude/settings.json`: the rules and permissions the coding agent worked under
