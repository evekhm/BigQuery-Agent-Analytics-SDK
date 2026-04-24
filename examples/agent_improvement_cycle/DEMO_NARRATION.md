# Demo Narration Transcript

## [OPENING — README visible on screen]

A well-designed agent should learn from its own mistakes. 
That's the paradigm this demo implements: a continuous self-improvement cycle where the agent's real-world failures
become the training data for its next version.

For this demo we use a company policy Q&A assistant, built with Google ADK and the BigQuery Agent Analytics Plugin.

It's deliberately simple: a single LLM agent with just two tools:
- `lookup_company_policy(topic)` — retrieves detailed policy data on a set of topics such as PTO, sick leave, 
- expenses, benefits, and holidays.
- `get_current_date()` — returns today's date and day of the week, so the agent can answer date-relative questions.

The agent's job is to answer employee questions — "How many PTO days do I get?", "What's the meal reimbursement limit?",
"When is the next company holiday?", and so on.

The V1 prompt is intentionally flawed. It tells the agent to "answer from the knowledge above" — a short, 
incomplete summary baked into the prompt — and to say "I don't know, contact HR" for anything not listed. 
The result: the agent ignores its own tools, even though those tools have all the answers. 
Users get vague deflections instead of useful information.

By running the self-improvement cycle, we'll watch the system detect these failures, 
generate correct answers using a teacher agent, optimize the prompt through the Vertex AI Prompt Optimizer, 
and produce a new version that actually uses the tools. The agent fixes itself.

---

## [SWITCH TO CLOUD SHELL — export PROJECT_ID, run setup.sh]
> Navigate to [Quick Start](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/tree/main/examples/agent_improvement_cycle#quick-start)

We will start from scratch in a new Google Cloud project. 

- I have repo checked out and inside the example agent directory
- I have set the `Project ID`
- I have run the setup script that:
  - checks Python and authentication, 
  - enables the BigQuery and Vertex AI APIs, 
  - installs dependencies, and 
  - creates the initial prompt in the Vertex AI Prompt Registry.
  - Creates `.env` and updates `config.json` files that are input for the flow.

---

## [cat .env and cat config.json]

Here's the `.env` environment configuration created from our setup. 

And here is the `config.json` — the declarative interface. So you could later swap it with another agent of your own.

---

## [SWITCH TAB — run_cycle.sh starts, banner displays]
> Navigate to [Solution](https://github.com/evekhm/BigQuery-Agent-Analytics-SDK/tree/feat/agent-improvement-cycle-demo/examples/agent_improvement_cycle#the-solution-learn-from-the-field)
Now lets run the improvement cycle.

As I mentioned earlier, the prompt has a flaw (highlight the prompt)

---
Out first step is to run the initial  **eval test cases**. Our ground truth and base for regression tests
* Then we **generate** traffic. In production, these come from the real users; for the demo, 
we use Gemini to come up with the possible user questions and run them against the agent. 
* Every session along with its metadata (token usage, latency, request/response, tool usage, trajectories and many more) is being logged to BigQuery via BigQuery Analytics plugin
* Then we **evaluate** each session quality — an LLM judge scores for usefulness and grounding
* Then we work on **improving** the agent, by fine-tuning its instructions via the prompt optimizer.
    * First we extract the _failed_ cases
    * Use a teacher agent to _generate the ground truth_
    * _Add_ those failed cases as extension to our _regression test set_ for evals
    * Use the **Vertex AI Prompt Optimizer** to produce a better prompt.
    * **Validate** the new prompt against the extended eva
* Finally, **measure** the improvement against fresh, unseen traffic — and iterate if needed.

---

## [STARTING PROMPT displayed]

Here's the V1 prompt. Notice the problem: it tells the agent to answer using *only the information above* — a short, incomplete list of policies. The agent has tools that can look up detailed policy data, but this prompt actively discourages it from using them. That's the flaw we want the cycle to fix.

---

## [PRE-FLIGHT check]

Before the cycle begins, the pre-flight check runs the golden eval set — three hand-written test cases — to make sure the current prompt doesn't break anything we already know works. All three pass. Good to go.

---

## [STEP 1 — Generate Synthetic Traffic]

Step one: Gemini generates ten diverse employee questions — things like "Do I need a doctor's note for four sick days?" and "What are the core hours for remote work?" These are intentionally different from the three golden test cases.

---

## [STEP 2 — Run Traffic Through Agent]

Step two sends those ten questions to the agent. Every session is logged to BigQuery through the BigQuery Agent Analytics Plugin. Watch the responses: for questions about parental leave, 401k, and holidays, the agent says "I don't have that information, contact HR." It has the tools to answer, but the V1 prompt told it not to use them.

---

## [STEP 3 — Evaluate Session Quality]

Step three is where the SDK earns its keep. The quality report script reads those sessions back from BigQuery and an LLM judge scores each one. Four sessions are marked unhelpful — the agent deflected instead of using its tools. One is partial. Five are meaningful. The baseline score: fifty percent meaningful. That's our starting point.

---

## [STEP 4 — Improve Prompt]

Step four is the core of the cycle. First, the five failed cases are extracted into the golden eval set, growing it from three to eight cases. These become the regression gate — any future prompt must pass all eight.

Next, a teacher agent re-answers each failed question. The teacher uses the same model and the same tools, but with a simple prompt that says: always use the tools first. The comparison is striking — where the original agent said "contact HR," the teacher correctly looks up parental leave, 401k matching, and holiday dates.

Those teacher answers become the ground truth. They're sent to the Vertex AI Prompt Optimizer, which generates an improved prompt that steers the agent toward tool usage.

The optimizer takes about a minute. When it returns a candidate, the regression gate kicks in — the candidate is tested against all eight golden eval cases. Every one passes. The prompt is promoted from V1 to V2.

---

## [STEP 5 — Measure Improvement]

Step five is the moment of truth. Ten fresh, never-before-seen questions are generated and run through the agent with the new V2 prompt. The quality report scores them from BigQuery.

Look at the responses now. Questions about vision coverage, parental leave for secondary caregivers, and the company holiday list — the agent uses its tools and gives direct, grounded answers. No more "contact HR."

---

## [CYCLE 1 RESULTS box displayed]

The results: Before, with V1, fifty percent meaningful. After, with V2, one hundred percent. Ten out of ten sessions scored as helpful and grounded — in a single cycle.

---

## [FINAL PROMPT displayed]

Here's the optimized V2 prompt. Compare it to V1: it explicitly requires tool usage for every question, provides a topic-mapping strategy so the agent knows to look up "benefits" when asked about 401k, and includes a critical rule — never say you don't have the information, always use the tools first.

This wasn't hand-written. It was generated by the Vertex AI Prompt Optimizer, validated by the regression gate, and measured against fresh traffic.

---

## [DONE summary — wall time, artifacts]

The full cycle completed in about six minutes. The golden eval set grew from three to eight cases, and all artifacts — quality reports, synthetic traffic, and ground truth — are saved for inspection.

---

## [CLOSING — README visible again]

That's the agent improvement cycle. Capture sessions with the BigQuery Agent Analytics Plugin, evaluate quality with the SDK, optimize prompts with Vertex AI, and measure the results — all automated, all repeatable. The golden eval set grows with every cycle, so failures you discover today become regression tests for tomorrow.
