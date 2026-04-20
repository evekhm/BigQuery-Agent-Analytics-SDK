# Agent Improvement Cycle Demo

Demonstrates a closed-loop agent improvement cycle powered by the
**BigQuery Agent Analytics SDK**. The cycle learns from real agent
sessions logged in production, not just synthetic test cases.

## The Problem

When you design eval cases for an agent, you are guessing what users
will ask. You cover the happy paths, maybe some edge cases, but you
cannot anticipate every real question. The agent ships, users interact
with it, and some of those interactions fail in ways your tests never
predicted.

## The Solution: Learn from the Field

This demo shows how to close that gap using two SDK components:

1. **`BigQueryAgentAnalyticsPlugin`** captures every real agent session
   (questions, tool calls, responses) into BigQuery automatically.
2. **`quality_report.py`** (the SDK's evaluation script) reads those
   logged sessions back from BigQuery, evaluates quality, and produces
   structured reports that can drive automated improvement.

The full cycle:

1. **Run** a Q&A agent that answers employee policy questions
2. **Log** every session to BigQuery via the plugin
3. **Evaluate** logged sessions using the SDK's quality evaluation
4. **Improve** the agent prompt based on what actually failed
5. **Extend** the eval suite with new cases derived from real failures,
   so regressions are caught before they reach users
6. **Repeat** until quality stabilizes

The hero moment: quality climbs from ~30% to ~90%+ across 3 cycles.

### Why This Matters

Static eval suites go stale. Users ask questions you never anticipated.
The plugin captures every real interaction, and the SDK's quality
evaluation scores them automatically. The improver reads those scores,
identifies the failure patterns, fixes the prompt, and generates new
eval cases so the same failures never recur.

Each cycle, the eval suite grows with cases sourced from actual
production failures. Over time, your tests reflect what users actually
ask, not what you imagined they would ask.

## Architecture

```
agent/
  agent.py       # ADK agent (company policy Q&A assistant)
  prompts.py     # Versioned prompts (V1 has intentional flaws)
  tools.py       # lookup_company_policy, get_current_date

eval/
  eval_cases.json   # Test questions with expected behavior
  run_eval.py       # Runs eval cases via ADK InMemoryRunner

improver/
  improve_agent.py  # Reads quality report, calls Gemini to fix prompt

reports/            # Generated reports and eval results

run_cycle.sh        # Orchestrator: eval -> quality report -> improve
setup.sh            # One-time setup (auth, deps, BigQuery dataset)
```

## How the Cycle Works

### The Agent

A Q&A agent built with Google ADK that answers employee questions about
company policies (PTO, sick leave, expenses, benefits, holidays). It has
two tools:

- `lookup_company_policy(topic)` - retrieves detailed policy data
- `get_current_date()` - returns today's date for relative date questions

Every session is logged to BigQuery via the `BigQueryAgentAnalyticsPlugin`,
capturing the full conversation trace: user question, tool calls, and
agent response.

### V1 Flaws (by design)

The v1 prompt has intentional problems that cause ~70% of sessions to fail:

| Flaw | Effect |
|------|--------|
| "Answer from knowledge above" | Agent ignores its tools entirely |
| No expense/holiday info in prompt | Agent says "I don't know" instead of looking it up |
| Vague "competitive benefits" | Agent deflects or hallucinates benefit details |
| No date handling guidance | Agent cannot resolve "next Friday" |

The tools themselves have all the data. The flaw is that the prompt
discourages the agent from using them.

### Step 1: Run Eval Cases (run_eval.py)

`run_eval.py` runs the agent **locally** using ADK's `InMemoryRunner`.
No server, no deployment, no containers. The agent runs entirely
in-process on your machine.

Here is what happens for each question in `eval/eval_cases.json`:

1. `InMemoryRunner` creates a new ADK session for the agent
2. The question is sent as a user message
3. The agent processes it like a real request: it calls Gemini on
   Vertex AI for reasoning, and executes its tools (`lookup_company_policy`,
   `get_current_date`) locally
4. `BigQueryAgentAnalyticsPlugin` (attached as a plugin to the runner)
   automatically captures the full session trace and writes it to BigQuery.
   This is the same plugin you would use in production. No extra logging
   code is needed.

The questions are hardcoded test cases that simulate real user traffic.
In production, real users generate sessions naturally through your agent's
serving endpoint. The plugin captures those sessions the same way.

```python
# From run_eval.py - this is how the agent runs locally:
runner = InMemoryRunner(
    agent=root_agent,
    app_name="company_info_agent",
    plugins=[bq_logging_plugin],   # <-- sessions auto-logged to BigQuery
)
# Send a question, get a response - just like a real user interaction
async for event in runner.run_async(user_id, session_id, user_message):
    ...
```

### Step 2: Evaluate Quality (quality_report.py)

The SDK's `quality_report.py` reads the sessions just logged to BigQuery
and scores each one:

- **response_usefulness**: Was the answer meaningful, partial, or unhelpful?
- **task_grounding**: Was it based on tool output, or did the agent hallucinate?

The `--app-name` flag filters to sessions from this agent only (ignoring
other agents sharing the same BigQuery dataset). `--output-json` produces
a structured report that the improver consumes programmatically.

### Step 3: Auto-Improve (improve_agent.py)

`improve_agent.py` reads the quality report JSON and calls Gemini to fix
the prompt:

1. Reads the quality report (which sessions failed and why)
2. Reads the current prompt from `agent/prompts.py`
3. Sends both to Gemini, asking it to fix the identified issues
4. Gemini returns a JSON with: an improved prompt, a summary of changes,
   and new eval cases that test the fixes
5. The script writes `PROMPT_V{N+1}` to `prompts.py` and updates
   `CURRENT_PROMPT` to point to it
6. New eval cases are appended to `eval/eval_cases.json`

On the next cycle, the agent uses the improved prompt, and the new eval
cases verify the fixes hold.

### Data Flow

```
Agent sessions  -->  BigQuery  -->  SDK quality evaluation  -->  improve_agent.py
(via plugin)         (storage)      (quality_report.py)          (prompt fix +
                                                                  new eval cases)
```

## Quick Start

### Prerequisites

- Python 3.10+
- Google Cloud project with billing enabled
- `gcloud` CLI authenticated (`gcloud auth application-default login`)

The setup script enables the required APIs automatically:
- **BigQuery API** (`bigquery.googleapis.com`)
- **Vertex AI API** (`aiplatform.googleapis.com`)

Your authenticated user or service account needs these IAM roles:

| Role | Why |
|------|-----|
| `roles/bigquery.dataEditor` | Create datasets, write agent session data |
| `roles/bigquery.jobUser` | Run BigQuery queries for evaluation |
| `roles/aiplatform.user` | Call Gemini models (agent + evaluator + improver) |

### 1. Configure environment

Set your GCP project:

```bash
export PROJECT_ID=my-project-id
```

All other variables have sensible defaults. Only set them if you need different values:

```bash
# BigQuery dataset for session logs (defaults shown)
DATASET_ID=agent_logs
DATASET_LOCATION=us-central1
TABLE_ID=agent_events

# Agent model (defaults shown)
DEMO_MODEL_ID=gemini-2.5-flash
DEMO_AGENT_LOCATION=us-central1
```

### 2. Run setup

```bash
./setup.sh
```

This installs dependencies, verifies credentials, and creates the
BigQuery dataset if it does not exist.

### 3. Run the demo

```bash
# Single improvement cycle
./run_cycle.sh

# Full demo: 3 cycles, watch the score climb from ~30% to ~90%
./run_cycle.sh --cycles 3

# Eval only (no improvement step)
./run_cycle.sh --eval-only
```

### 4. Inspect results

After a run, check the `reports/` directory:

```bash
# Quality report JSON (consumed by the improver)
cat reports/quality_report_cycle_1.json | python3 -m json.tool | head -20

# See how the prompt evolved
cat agent/prompts.py

# See new eval cases added by the improver
cat eval/eval_cases.json
```

### Reset to V1

To start over, reset the prompt and eval cases to their original state:

```bash
git checkout -- agent/prompts.py eval/eval_cases.json
```

## SDK Features Used

- **`BigQueryAgentAnalyticsPlugin`** - logs every agent session (user
  message, tool calls, agent response) to BigQuery automatically
- **`quality_report.py --app-name`** - scopes evaluation to sessions from
  this specific agent, filtering out other agents sharing the same dataset
- **`quality_report.py --output-json`** - structured quality report for
  automated consumption by the improver
- **Categorical evaluation metrics** - `response_usefulness` (was it
  helpful?) and `task_grounding` (was it based on tool output?)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_ID` | from `gcloud` | Google Cloud project ID (required) |
| `DATASET_ID` | `agent_logs` | BigQuery dataset for session logs |
| `DATASET_LOCATION` | `us-central1` | BigQuery dataset location |
| `TABLE_ID` | `agent_events` | BigQuery table name |
| `DEMO_MODEL_ID` | `gemini-2.5-flash` | Model for the demo agent |
| `DEMO_AGENT_LOCATION` | `us-central1` | Vertex AI location |
