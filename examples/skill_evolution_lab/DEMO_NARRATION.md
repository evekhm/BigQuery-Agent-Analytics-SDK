# Your Agent Can Write Its Own Skill

> A follow-up to *"Your Agent Can Fix Its Own Prompt."* The first post fixed an
> agent's failures with a teacher model and a prompt optimizer. This post shows a
> different method: the agent reads its own conversation traces — successes and
> failures — and extracts a structured, versioned skill. No teacher, no managed
> optimizer. It is packaged as this runnable example in the
> [BigQuery Agent Analytics SDK](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK).

## From fixing failures to extracting a skill

In the [first post](https://medium.com/google-cloud/your-agent-can-fix-its-own-prompt-heres-how),
the agent learned from its mistakes by knowledge distillation: take the questions
it got wrong, have a **teacher model** generate the correct answers, and feed the
gap to a prompt optimizer that rewrites the system prompt. It works — but it
needs a teacher that already knows the answers, it only learns from failures, and
the output is a flat prompt string you can't easily diff.

What if the agent could analyze *all* its conversations — successes and failures
— and write its own instruction manual, with no teacher to supply the answers?
That is **skill evolution**. A fleet of analysts reads the traces: each failure
gets an analyst that asks "what went wrong, and what rule prevents it?", and
sampled successes get one that asks "what worked, and should we reinforce it?".
An inductive consolidator merges the rules that recur into a single versioned
`SKILL.md`. The method comes from two 2026 papers — Trace2Skill and AutoSkill —
and the engine ships as a standalone, importable script in the SDK
([`scripts/skill_evolution.py`](../../scripts/skill_evolution.py)).

## What is a skill?

A skill is a structured markdown document (`SKILL.md`): YAML frontmatter for
versioning, a markdown body for instructions.

```markdown
---
name: company-policy
description: Answers employee questions about company policies.
metadata:
  version: "0"
  author: human
---

You are a helpful company information assistant.
...
```

Because it's plain, versioned markdown, an evolved skill is a **reviewable diff**
with named sections (knowledge, response rules, anti-patterns) — you can read
each rule the agent learned and see exactly what changed between versions.
Google's [ADK](https://adk.dev) and the Gemini Enterprise Agent Platform
[Skill Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/skill-registry)
treat skills as a first-class, versioned concept; in this example V0 is the
registry's first revision and the evolved V1 is the second.

## The evolution engine

The engine takes scored conversations in and produces an evolved skill out:

```text
Quality report (scored conversations)
   |
   v
Partition: successes vs failures (parroted "recoveries" count as failures)
   |
   +-- Error analysts  (one per failure):  "what went wrong? what rule prevents it?"
   +-- Success analysts (sampled):         "what pattern worked? reinforce it?"
   |
   v
Patch consolidator  (prevalence-weighted semantic union, conflict-resolved)
   |
   v
Evolved SKILL.md (version bumped)
```

Analysts run **in parallel** and **independently** (each sees one trajectory, no
contamination); the consolidator is **inductive** (keeps patterns that recur,
drops one-offs). This follows [Trace2Skill](https://arxiv.org/abs/2603.25158)
(parallel analysts + inductive consolidation) and
[AutoSkill](https://arxiv.org/abs/2603.01145) (versioned skill evolution as a
semantic merge). The engine is engine-only: it consumes a report *dict* and
returns skill text — it does not import `quality_report`, so the two compose but
stay independent.

## The demo: one agent, one tool, one realistic flaw

A company-policy Q&A assistant ([`agent/agent.py`](agent/agent.py)) — a single
Gemini model with one tool, `lookup_company_policy`, that can look up **every**
policy and benefit (automatic function calling). Its V0 skill
([`skills/SKILL.v0.md`](skills/SKILL.v0.md)) bakes in a few facts plus an
anti-hallucination guardrail:

```text
You have the following knowledge about company policies:
- PTO: 20 days per year, accrued monthly. Up to 5 unused days roll over.
- Sick leave: 10 days per year, does not roll over.
- Remote work: Up to 3 days per week with manager approval.
- Benefits: The company offers competitive benefits.

Answer questions using only the information above. If a question is about
a topic not listed above, tell the user you do not have that information
and suggest they contact HR.
```

That last paragraph is the flaw. "Answer only from the above, else contact HR"
stops hallucination — and also stops the agent from using the tool it already
has. Ask *"what's the 401k match?"* and it says *"I do not have that
information, please contact HR"* — without ever trusting the tool that knows the
answer (4% match, $75/day meals, $1,500 family HSA, ...).

The tool already returns the right answers; only the skill is wrong. The model,
tools, and questions stay fixed across V0 and V1 — **only the skill file
changes** — so any quality delta is attributable to the skill.

## The cycle: learning from users

The signal that drives evolution is **user conversations**. In production those
are the real sessions your agent already logs to BigQuery. For the demo we
simulate them with two question sets the agent runs against
([`eval/`](eval/)): an *evolve* set (the skill learns from these) and a disjoint
*held-out test* set (the headline number is measured on these). Multi-turn cases
add user pushback, where a user asserts a wrong figure and a good agent must
re-verify rather than cave.

One command runs the whole cycle:

```bash
cd examples/skill_evolution_lab
./setup.sh YOUR_PROJECT_ID us-central1
./run_e2e_demo.sh
```

Deploy flawed V0 → generate traffic over the evolve + held-out sets → score
against the golden Q&A answer key → run the evolution engine on the failures →
deploy the evolved V1 → re-score the held-out set → restore V0.

The engine reads the failing trajectories and writes a new skill, size-capped to
stay honest. Here is (abridged) the skill it learned in the recorded run — small,
legible, tool-first, with no keyword tables:

```markdown
## Instructions
- **Tool Use & Fallback:** If a user asks about a company policy or detail not
  explicitly listed in your provided knowledge above, you MUST first use your
  available tools to search for the information. Only tell the user you do not
  have the information ... if your tool search yields no relevant results.

## Anti-Patterns
- **Premature HR Deflection:** Do not immediately tell the user you lack
  information or direct them to HR for policy topics not listed in your static
  knowledge. You must always attempt to use your available tools first.
```

It rediscovered the rule that matters: be tool-first, and don't defer to HR for
something the tool can answer.

## <a name="anti-parroting"></a>Corrections are not answers: the anti-parroting rule

When a user corrects the agent, the conversation can end two ways that both look
fine. The agent can re-query its tool, confirm the fact, and answer from the
tool. Or it can just say "you're right" and repeat what the user said. The
second is **parroting**: the final message contains the right fact, so a naive
scorer calls it a success — but the agent verified nothing. In production this is
the failure that bites: the agent becomes a yes-man to a confident, wrong user.

The lab exercises this directly.
[`eval/questions_corrections.json`](eval/questions_corrections.json) (teach) and
[`eval/questions_corrections_heldout.json`](eval/questions_corrections_heldout.json)
(held-out) are multi-turn cases where the user asserts a *wrong* figure ("the
401k match is 6%, right?"). The flawed V0, with no fact to stand on, declines or
caves; the evolved V1 re-verifies with the tool and holds the correct value.

It is a **detect-then-learn** pipeline, and both halves live in this SDK:

- **Detection** — [`scripts/quality_report.py`](../../scripts/quality_report.py),
  the `_TURN_TAGGER_PROMPT` (`--tag-turns`). It splits a conversation at each
  correction and labels what the agent did next: `recovered` (used a tool / cited
  a source), `parroted` (only echoed the user's fact), or `not_recovered`. An
  answer counts as recovery *only* if the agent verified independently.
- **Learning** — [`scripts/skill_evolution.py`](../../scripts/skill_evolution.py).
  A parroted turn is reclassified from success to failure
  (`_has_parroted_recovery`), so the engine can't reinforce it. The error analyst
  records the root cause `PARROTING`, and the success analyst refuses to extract a
  pattern from a parroted recovery (`NO_PATCH`). The learned rule: when corrected,
  verify with a tool — don't just agree.

`compare_runs.py` reports the corrections as their own line and counts parroted
sub-trajectories before and after evolution. (In the recorded run V0 *declined*
on corrections rather than caving, so the tool-first rule alone recovered them;
the `PARROTING` machinery is the safety net that prevents the opposite failure —
learning to agree.)

## Results: V0 → V1 across three Gemini-3 models

Numbers from this example, on the **held-out** set the engine never trained on.
**Correctness** is graded against the known answer (the LLM judge anchored on the
golden Q&A); **grounding** is the share of answers that actually called the tool
(a deterministic count).

```text
Model                    V0 correct   V1 correct    grounding V0 -> V1
----------------------   ----------   ----------    ------------------
gemini-3-flash-preview      23.8%        100%            29% -> 86%
gemini-3.1-flash-lite       14.3%        100%             0% -> 90%
gemini-3.1-pro-preview      19.0%        100%             5% -> 86%
```

Every model recovers to 100% on the held-out set, with zero hallucinated answers
introduced — and the grounding column shows *why*: V0 barely calls the tool
(0–29% of answers), because the flawed skill tells it not to; V1 calls it on
~90%. The flawed V0 has a harsh baseline here because the held-out set is mostly
benefits/expenses topics that are *not* in V0's baked summary, so V0 declines on
nearly all of them; once the skill is tool-first, the same tool answers them.
(A companion run on a different question mix shows a higher baseline; the
direction — large, grounded recovery — is the same.)

## What it actually took (the traps)

Almost everything below is a thing we got wrong first.

- **A bare prompt on a capable model has no headroom.** Our first design used a
  bare prompt on a capable model with wired tools. It scored ~90% out of the box,
  because a smart model just uses its tools — nothing for a skill to fix. The fix
  isn't a weaker model; it's a *real, correctable flaw* (the "contact HR" prompt).
  Without it, there is no demo.
- **The most capable model fails the most.** Counterintuitively, a stronger model
  follows the bad instruction more faithfully, so it defers on more and has the
  *most* headroom for the skill to recover. The "only weak models need the skill"
  intuition is backwards.
- **A judge without ground truth lies.** An LLM judge scoring "usefulness"
  *without* an answer key mislabels correct, tool-grounded answers as unhelpful —
  worst on the most capable model, whose answers are most verbose. The fix is
  [`eval/eval_spec.json`](eval/eval_spec.json): supply `{question, expected_answer}`
  pairs and grade against them (`golden_eval_summary.matched_meaningful_rate`).
  Treat any no-ground-truth "quality score" as an estimate, not a result.
- **Overfitting shows up as bloat.** Against a task with no real general fix, the
  algorithm doesn't fail loudly — it overfits quietly into large skills full of
  keyword-mapping tables. A skill that enumerates cases instead of stating a rule
  is the tell-tale sign you're optimizing the judge, not teaching the agent.
  `--max-chars` keeps the extracted skill small enough to read and believe.

### What the papers had already paid for

Three of our bugs were named and solved in the source papers, and the fixes are
in the engine:

- **Held-out validation.** Measuring improvement on the same questions the patches
  came from is textbook overfitting. Trace2Skill insists the evolve and test sets
  be disjoint — every headline number here is on a held-out set.
- **Sequential drift.** Re-evolving from the already-evolved skill round after
  round makes quality collapse. Trace2Skill: parallel consolidation from a frozen
  base beats sequential re-editing.
- **Rewrite-from-scratch content loss.** A consolidator that rewrites the whole
  skill silently drops rules. AutoSkill's `P_merge` prescribes a *semantic union*:
  keep every existing check unless a patch overrides it. The engine's diff-guard
  rejects any candidate that drops a base section.

## What a skill can't fix (a separate story)

A skill can only fix *behavior*. It cannot invent a fact the tools don't have or
build a capability that doesn't exist — and pretending otherwise is how demos
overstate themselves.

The complementary half of an end-to-end quality loop is to take every failure the
skill *can't* fix and attribute it to an owner:

- a needed fact is missing from the data → **KNOWLEDGE** (add the doc / RAG source)
- a tool returned the wrong value, or no tool exists → **ENG** (fix/build the tool)
- the request is out of scope → **PRODUCT** (a scope decision, a clean decline)

A triage pass classifies each *residual* failure and files it as a routed work
item (for example, a labeled GitHub issue), while the evolution step fixes the
behavioral failures automatically — so a single run both heals what it can and
hands you an attributed backlog of what it can't. That is the difference between
a quality *score* and a quality *loop*.

**This routing/triage system is not part of this example or the SDK.** It is a
separate demo and write-up of its own (the "in an earlier multi-agent run this
opened a PR for the fix plus routed issues for the rest" idea). This post is
scoped to the self-contained skill loop — flawed V0 → evolved V1, grounded and
versioned. We recommend pairing it with a triage pass in production, and we'll
cover that end-to-end separately.

## From the demo to production

The demo simulates users because we start from zero. In production you don't have
to: your agent already logs every real conversation to BigQuery, and that is the
traffic the loop runs on. The engine is the same; only the source of the
conversations changes. Score recent real sessions against the same golden Q&A,
evolve when gaps pile up, and open a PR with the new `SKILL.md` and a
before/after table — versioned in the Skill Registry, reviewed as a diff, gated
by the eval before it redeploys.

## How this relates to the research

[Trace2Skill](https://arxiv.org/abs/2603.25158) (parallel analysts + inductive
consolidation) contributes the frozen-base consolidation, content-preserving
guardrails, and held-out split; [AutoSkill](https://arxiv.org/abs/2603.01145)
contributes the versioned semantic-merge (`P_merge`) operator. This example
differs in packaging: a runnable loop that learns from conversations, a readable
versioned skill instead of a flat prompt, ground-truth scoring so the numbers
hold up, and Skill Registry versioning.

## Running it yourself

```bash
cd examples/skill_evolution_lab
./setup.sh YOUR_PROJECT_ID us-central1     # writes .env, resets to V0
./run_e2e_demo.sh                          # V0 -> evolve -> V1 -> compare, restore V0

# Try other models (the agent under test):
AGENT_MODEL=gemini-3.1-flash-lite ./run_e2e_demo.sh
AGENT_MODEL=gemini-3.1-pro-preview ./run_e2e_demo.sh

# Version the skill in the Skill Registry (V0 = revision 1, V1 = revision 2):
WITH_REGISTRY=1 SKILL_ID=skill-lab-policy ./setup.sh YOUR_PROJECT_ID us-central1
WITH_REGISTRY=1 SKILL_ID=skill-lab-policy ./run_e2e_demo.sh
WITH_REGISTRY=1 SKILL_ID=skill-lab-policy ./reset.sh   # revert local + registry to V0
```

Each run deploys the flawed V0, generates and scores traffic, evolves a tool-first
skill, re-scores the held-out set, prints the V0 → V1 comparison, and restores V0.
See [`README.md`](README.md) for the file map and [`VERIFICATION.md`](VERIFICATION.md)
for a recorded run.

## The takeaway

The first post fixed an agent's failures with a teacher model and a prompt
optimizer. This post removes the teacher. The agent reads its own conversations,
learns from the ones that worked and the ones that didn't, and writes itself a
structured, versioned skill you can read and diff. A skill only fixes behavior,
so the loop is also honest about what a new rule can't touch — a missing tool, a
missing fact. In the demo the conversations are simulated; in production they are
real. Either way, the agent turns the way people use it into a better version of
itself.
