# Agent Improvement Cycle - Demo Voice Script

**Duration:** ~5-7 minutes
**Format:** Live terminal walkthrough

---

## INTRO (30s)

Here's the problem. You build an agent, you write some eval cases, you ship it.
Users start asking questions you never anticipated. Your eval suite goes stale.
You have no idea what's failing in production until someone complains.

What if the agent could learn from its own mistakes? Not retraining. Not
fine-tuning. Just... reading what went wrong and fixing its own prompt.

That's what this demo shows. A closed-loop improvement cycle powered by the
BigQuery Agent Analytics SDK. Three steps, fully automated. Let's run it.

---

## Show the V1 Prompt (30s)

**Command:** `cat agent/prompts.py`

Let's look at our starting point. This is the agent's prompt, version 1.

We put some flaws in here on purpose, but these are exactly the kind of
mistakes you see in real projects:

- The prompt says "answer from the knowledge above" instead of calling tools.
  Classic prototyping shortcut that never got cleaned up.
- It covers PTO, sick leave, remote work, but skips expenses and holidays.
  Someone added those tools later, but forgot to update the prompt.
- Benefits just says "competitive." Copy-pasted from the company website.
  The agent will either make things up or say "I don't know."
- No date handling. There's a `get_current_date` tool, but the prompt
  never mentions it. "Is next Friday a holiday?" won't work.

The tools have all the answers. The prompt just doesn't let the agent use
them. And without production telemetry, you wouldn't know until users
start complaining.

---

## Show Eval Cases (20s)

**Command:** `cat eval/eval_cases.json`

Here are our test questions. Ten of them.

Three are easy. "How many PTO days do I get?" The prompt has that info, so even
V1 should answer correctly. But seven of them hit the blind spots. "What's the
meal reimbursement limit?" "Does the company match 401k?" "What are the holidays
this year?" V1 will deflect all of these.

---

## Run Cycle 1 - Step 1: Simulate User Traffic (45s)

**Command:** `./run_cycle.sh --cycles 3`

Step 1: Simulate user traffic. The script sends each test question to the agent.
It uses ADK's InMemoryRunner, which means the agent runs entirely locally in
this Python process. No server, no deployment. But it does make real calls to
Gemini on Vertex AI for reasoning, and the tools execute locally against
hardcoded policy data.

Here's the key part: every session is automatically logged to BigQuery by the
BigQueryAgentAnalyticsPlugin. Same plugin you'd use in production. The full
trace goes in: the user question, every tool call, every LLM response. Zero
extra logging code.

*(as output scrolls)* You can see it processing each question. "How many PTO
days?" gets a real answer. But "What is the meal reimbursement limit?"... the
agent says "I don't have that information, contact HR." Because the prompt told
it to.

---

## Cycle 1 - Step 2: Evaluate Quality (45s)

Step 2: Evaluate quality. The SDK's quality report reads those sessions back
from BigQuery and scores each one on two dimensions.

First, response usefulness: was the answer actually helpful, partially helpful,
or unhelpful? Second, task grounding: did the agent base its answer on tool
output, or did it hallucinate?

*(point to the quality summary)* There's our score. About 30% meaningful. Seven
out of ten questions got unhelpful responses. The agent had the tools to answer
every single one, but the prompt blocked it.

---

## Cycle 1 - Step 3: Auto-Improve (45s)

Step 3: Auto-improve. The script takes that quality report and sends it to
Gemini along with the current prompt. Gemini sees which sessions failed and
why. "The agent deflected expense questions even though lookup_company_policy
has expense data." "The agent said 'competitive benefits' instead of looking
up specific plan details."

Gemini rewrites the prompt. It adds instructions to always call
lookup_company_policy before answering policy questions. It adds guidance for
expenses, holidays, benefits. And it generates new eval cases that specifically
test those fixes, so if they break in a future cycle, we catch it immediately.

But here's the important part: we don't just trust the LLM's output blindly.
Before writing anything to disk, the improver runs two validation steps:

1. **Prompt validation via a second Gemini call.** We send both the original
   and the improved prompt to a reviewer LLM and ask: did you preserve the
   key topics? Are the tool references still there? Is this coherent, or did
   the model hallucinate something unrelated? If validation fails, it retries
   the whole improvement automatically.

2. **Eval case schema validation.** Every new eval case the LLM generates
   must have the required fields: `id`, `question`, `category`,
   `expected_tool`. If the model returns a malformed case, it gets skipped
   with a warning instead of silently breaking the next cycle.

*(point to output)* V1 becomes V2. The new prompt is written to prompts.py, and
the validated eval cases are appended to eval_cases.json.

---

## Cycle 2 (30s)

Now cycle 2 starts. Same three steps, but the agent is running with the
improved V2 prompt. And there are more eval cases now, the ones Gemini added.

*(as it runs)* Watch the responses. "What's the meal reimbursement limit?" Now
it calls lookup_company_policy, gets "$75 per day during business travel."
"Does the company match 401k?" It looks it up: "4% match, vested after one
year."

*(point to quality score)* The quality score jumps. We're at about 70-80% now.
Maybe there are still a couple of edge cases. The date question, the one about
"Is next Friday a holiday?" That might still be tricky.

---

## Cycle 3 (30s)

Cycle 3. The prompt gets refined again. The last edge cases get fixed. Date
handling instructions added. Holiday lookup combined with get_current_date.

*(point to final score)* 90%+ meaningful. From 30% to 90% in three automated
cycles. No human prompt engineering. The agent learned from its own production
data.

---

## Wrap-Up (30s)

**Command:** `git diff agent/prompts.py`

Let's look at what changed.

Three prompt versions. Each one targeted at specific failures found in the
previous cycle's sessions. And the eval suite grew from 10 cases to about
16-18, each new case sourced from a real failure.

This is the whole point. Static eval suites go stale. Users ask questions you
didn't anticipate. The BigQuery Agent Analytics Plugin captures every real
interaction. The SDK's quality evaluation scores them automatically. And the
improver closes the loop.

The eval suite grows with cases from actual failures. Over time, your tests
reflect what users really ask, not what you imagined they would ask.

That's the cycle.
