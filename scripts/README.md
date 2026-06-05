# Scripts

Standalone scripts for the BigQuery Agent Analytics SDK.

| Script | Description |
|--------|-------------|
| [quality_report](#quality-report) | LLM-as-a-judge evaluation over agent sessions |
| [skill_evolution](#skill-evolution) | Evolve a versioned `SKILL.md` from a scored quality report |
| [latency_report](#latency-report-1) | Timing tree and waterfall for agent traces with A2A stitching |

## Quality Report

Runs LLM-as-a-judge evaluation over agent sessions stored in BigQuery
and produces a quality report with per-agent breakdown, unhelpful session
analysis, and category distributions.

### Prerequisites

- Python 3.11+
- BigQuery Agent Analytics SDK installed (`pip install bigquery-agent-analytics`)
- GCP authentication configured (`gcloud auth application-default login`)
- Agent traces already stored in a BigQuery table

### Environment Variables

Create a `.env` file in the repo root or export these variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `PROJECT_ID` | Yes | GCP project containing the traces table |
| `DATASET_ID` | Yes | BigQuery dataset name |
| `TABLE_ID` | Yes | BigQuery table name (e.g. `agent_events`) |
| `DATASET_LOCATION` | Yes | BigQuery dataset location (e.g. `us-central1`) |
| `EVAL_MODEL_ID` | No | Model for evaluation (default: `gemini-2.5-flash`) |
| `GOOGLE_CLOUD_PROJECT` | No | GCP project for Vertex AI (defaults to `PROJECT_ID`) |
| `GOOGLE_CLOUD_LOCATION` | No | Vertex AI location (default: `global`) |

Example `.env`:

```bash
PROJECT_ID=my-gcp-project
DATASET_ID=agent_logs
TABLE_ID=agent_events
DATASET_LOCATION=us-central1
EVAL_MODEL_ID=gemini-2.5-flash
```

### Usage

```bash
# From the repo root:
./scripts/quality_report.sh                         # evaluate last 100 sessions
./scripts/quality_report.sh --limit 500             # evaluate last 500 sessions
./scripts/quality_report.sh --time-period 7d        # evaluate last 7 days
./scripts/quality_report.sh --report                # also generate markdown report
./scripts/quality_report.sh --no-eval               # browse Q&A only (no evaluation)
./scripts/quality_report.sh --persist               # persist results to BigQuery
./scripts/quality_report.sh --model gemini-2.5-pro  # use a specific model
./scripts/quality_report.sh --samples 20            # show 20 sessions per category
./scripts/quality_report.sh --samples all           # show all sessions per category
./scripts/quality_report.sh --app-name my_agent     # filter to a specific agent app
./scripts/quality_report.sh --session-ids-file ids.json  # evaluate specific sessions
./scripts/quality_report.sh --output-json report.json    # write structured JSON output
./scripts/quality_report.sh --threshold 15          # unhelpful rate warning at 15%
./scripts/quality_report.sh --config config.json    # scope-aware eval with config
```

Or run the Python script directly:

```bash
python scripts/quality_report.py --limit 50 --report
```

### Output

**Console output** includes:
- Per-session details grouped by category (unhelpful, partial, meaningful)
- Per-agent quality table with helpful/unhelpful rates and status indicators
- Unhelpful contribution ranking
- Category distributions
- Execution details (elapsed time, execution mode)

**Markdown report** (`--report` flag) is saved to `scripts/reports/` and includes
all the above in a structured markdown format suitable for sharing or archiving.

**Log files** are saved to `scripts/reports/` for each eval run.

### Filtering

By default, the script evaluates the most recent sessions by time. Two
additional filters are available for targeted evaluation:

- **`--app-name`** filters to sessions from a specific agent. Matches the
  `root_agent_name` attribute set by `BigQueryAgentAnalyticsPlugin`.
- **`--session-ids-file`** evaluates only the sessions listed in a JSON file.
  Accepts either a list of `{"session_id": "..."}` objects (the output of
  `run_eval.py`) or a plain list of ID strings. When session IDs are provided,
  the script filters directly by ID instead of relying on time-based queries,
  which avoids picking up stale sessions from prior runs.

These filters can be combined (e.g. `--app-name my_agent --session-ids-file ids.json`).

### Metrics

The evaluation uses two categorical metrics:

- **response_usefulness** - Whether the agent's response provides a genuinely
  useful answer. Categories: `meaningful`, `declined`, `unhelpful`, `partial`.

- **task_grounding** - Whether the response is grounded in tool-retrieved data
  or fabricated. Categories: `grounded`, `ungrounded`, `no_tool_needed`.

The **`declined`** category is always available — the LLM judge can classify
polite refusals of out-of-scope questions as correct behavior rather than
marking them as `unhelpful`.

### Scope-Aware Evaluation (`--config`)

For more accurate scope evaluation, provide a config file that tells the
LLM judge exactly which topics your agent intentionally does not handle:

```bash
./scripts/quality_report.sh --config agent_context.json --report
```

The script also auto-discovers `eval/data/agent_context.json` relative to
the repo root or script directory, so `--config` is only needed to point
at a non-default location.

Create a JSON config file with `scope_decisions`:

```json
{
  "scope_decisions": [
    {
      "topic": "stock_options",
      "decision": "out_of_scope",
      "reason": "No tool or data source covers equity compensation"
    },
    {
      "topic": "salary_bands",
      "decision": "out_of_scope",
      "reason": "Confidential compensation data"
    },
    {
      "topic": "promotions",
      "decision": "out_of_scope",
      "reason": "No tool covers career progression"
    }
  ]
}
```

Without a config, the LLM judge can still classify obvious declines as
`declined`, but it won't know which specific topics are out of scope. With
the config, the judge is told exactly which topics are out of scope, so it
can correctly classify polite refusals as `declined` (correct behavior)
rather than `unhelpful` (a bug).

### A2A Support

The script automatically detects and resolves responses from remote A2A
(Agent-to-Agent) agents by extracting `A2A_INTERACTION` events from traces.


### Sample report output

[Sample quality report](sample_quality_report.md)

---

## Latency Report

Fetches agent traces from BigQuery and renders a hierarchical timing tree
with per-span latency and a waterfall timeline. Automatically stitches
A2A (Agent-to-Agent) remote sessions to show full cross-agent latency
breakdown — including LLM call times inside remote agents that would
otherwise appear as a black box.

### Usage

```bash
./scripts/latency_report.sh                              # latest trace
./scripts/latency_report.sh --limit 5                    # last 5 traces with summary
./scripts/latency_report.sh --time-period 1h             # traces from the last hour
./scripts/latency_report.sh --session <session_id>       # specific session
./scripts/latency_report.sh --app-name my_agent          # filter by root agent name
./scripts/latency_report.sh --verbose                    # show questions and responses
./scripts/latency_report.sh --no-stitch                  # skip A2A session stitching
./scripts/latency_report.sh --env path/to/.env           # use a specific .env file
```

Or run the Python script directly:

```bash
python scripts/latency_report.py --limit 5 --time-period 1h
python scripts/latency_report.py --env path/to/.env --limit 5
```

### Output

The script produces three views for each trace:

1. **Timing tree** — hierarchical span view with latency annotations,
   tool names, and A2A boundary markers
2. **Waterfall chart** — ASCII bar chart showing time distribution
3. **SDK trace tree** — the SDK's built-in `trace.render()` output

When multiple traces are fetched (`--limit > 1`), a **summary table**
shows aggregate latency statistics (avg, P50, P95, min, max) and
per-agent breakdown.

### A2A Session Stitching

When a supervisor agent calls a remote agent via A2A, the parent trace
only records `AGENT_STARTING` and `AGENT_COMPLETED` for the remote
agent — the internal LLM and tool spans are logged in a separate
BigQuery session.

The script automatically:
1. Detects `A2A_INTERACTION` events in the parent trace
2. Extracts the remote session ID from `content.metadata.adk_session_id`
3. Fetches the remote agent's spans and inlines them as children

Use `--no-stitch` to disable this behavior.

### Sample report output

[Sample latency report](sample_latency_report.md)

## Skill Evolution

Evolves an agent's skill from its own conversation traces. It reads a scored
quality report (the output of [Quality Report](#quality-report)), partitions the
trajectories into successes and failures, runs a fleet of parallel, independent
analysts (one per failure; sampled successes), and consolidates the recurring
rules into a new, version-bumped `SKILL.md`. No teacher model supplies the
answers — the agent learns what to fix and what to keep from how it was used.

The method follows two 2026 papers — [Trace2Skill](https://arxiv.org/abs/2603.25158)
(parallel analysts + inductive consolidation, held-out validation) and
[AutoSkill](https://arxiv.org/abs/2603.01145) (versioned skill evolution as a
semantic merge). It is engine-only: it consumes a report *dict* and returns
skill text — it does not import `quality_report`, so the two compose but are
independent.

### Prerequisites

Vertex AI via the google-genai client. Set `GOOGLE_CLOUD_PROJECT` and
`GOOGLE_CLOUD_LOCATION` (Gemini 3.x models use the `global` endpoint), and
authenticate with ADC (`gcloud auth application-default login`).

### Python API

`skill_evolution.py` is importable the same way as `quality_report` (e.g. via
`import_sdk_module("skill_evolution")`):

```python
import skill_evolution

evolved = skill_evolution.evolve_skill(
    report,            # a quality report dict (or path) with golden_qa scoring
    current_skill,     # the current SKILL.md text (the base to merge into)
    model="gemini-2.5-pro",
    candidates=3,      # best-of-N consolidation
    max_chars=3500,    # keep the skill small (overfitting shows up as bloat)
    score_fn=None,     # optional (skill_text)->float to pick/gate the best candidate
)
```

With no `score_fn` the engine returns the median-size viable candidate; the
held-out re-score is the proof. Guardrails reject candidates that drop a base
section, leak placeholders, or truncate.

### CLI

```bash
python scripts/skill_evolution.py \
    --report quality_report.json \
    --skill path/to/SKILL.md \
    --model gemini-2.5-pro --candidates 3 --max-chars 3500 \
    -o evolved_SKILL.md
```

### Corrections are not answers (anti-parroting)

When a user corrects the agent, an answer counts as a *recovery* only if the
agent re-verified with a tool. If it merely echoed the user's claim, the turn
tagger (`quality_report.py --tag-turns`) labels it `parroted`; this engine
reclassifies a parroted "recovery" as a failure (`_has_parroted_recovery`), the
error analyst records the root cause `PARROTING`, and the success analyst
refuses to extract a pattern from it (`NO_PATCH`). The learned rule: when
corrected, verify with a tool — don't just agree.

### Runnable example

See [`examples/skill_evolution_lab/`](../examples/skill_evolution_lab/) for an
end-to-end demo: a flawed V0 skill → traffic → golden-Q&A scoring → `evolve_skill`
→ tool-first V1, with Skill Registry versioning.