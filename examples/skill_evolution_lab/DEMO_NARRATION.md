# Your Agent Can Write Its Own Skill

> A follow-up to "Your Agent Can Fix Its Own Prompt." The first post fixed an agent's failures with a teacher model and a prompt optimizer. This post shows a different method: the agent reads its own conversation traces — successes and failures — and extracts a structured, versioned skill. No teacher, no managed optimizer. Tested across three Gemini-3 models.

## From fixing failures to extracting a skill

In the [first post](https://medium.com/google-cloud/your-agent-can-fix-its-own-prompt-heres-how),
the agent learned from its mistakes. The method was knowledge distillation:

- Take the questions the agent got wrong.
- Have a **teacher model** generate the correct, tool-grounded answers.
- Feed the (question, wrong answer, correct answer) examples to Vertex AI's
  Prompt Optimizer.
- The optimizer rewrites the system prompt to close the gap, gated by a golden
  eval set.

It works. A company-policy agent went from 64% to 99% useful answers in one run.
But the method has limits:

- **It needs a teacher.** Something has to already know the right answers. In the
  demo one model played both roles; in production the teacher is a stronger model
  or a human reviewer.
- **It only learns from failures.** Every successful conversation is thrown away,
  even though successes show what the agent should keep doing.
- **The output is a flat prompt string.** The optimizer hands back a rewritten
  prompt. You can't easily see which rule changed, or why.

What if the agent could analyze *all* its conversations — successes and failures
— and write its own instruction manual, with no teacher to supply the answers?

That is what this post builds. We call it **skill evolution**.

Instead of distilling answers from a teacher, the agent extracts a **skill** from
its own traces. A fleet of analysts reads the conversations: each failure gets an
analyst that asks "what went wrong, and what rule prevents it?", and sampled
successes get an analyst that asks "what worked, and should we reinforce it?". An
inductive consolidator merges the rules that recur into a single versioned
`SKILL.md` — structured into named sections, so you can see exactly which rule
each version added. The method comes from two 2026 papers — Trace2Skill and AutoSkill — and
the engine now ships as a standalone script in the
[BigQuery Agent Analytics SDK](https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK)
([`scripts/skill_evolution.py`](../../scripts/skill_evolution.py)), so you can
run it on your own agent. This example is the runnable demo.

## What is a skill?

A skill is a structured markdown document (`SKILL.md`) that replaces the flat
prompt string from the first post. YAML frontmatter for versioning, a markdown
body for instructions:

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

Because it's plain, versioned markdown, an evolved skill is a reviewable diff.
Unlike a flat prompt string, it has named sections — knowledge, response rules,
anti-patterns — so you can read each rule the agent learned and see exactly what
changed between versions. Google's [ADK](https://adk.dev) and the Gemini
Enterprise Agent Platform
[Skill Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/skill-registry)
treat skills as a first-class, versioned concept, so this isn't a custom
framework. In this example, V0 is the registry's first revision and the evolved
V1 is the second.

## The evolution engine

The engine takes scored conversations in and produces an evolved skill out:

```text
Quality report (scored conversations)
   |
   v
Partition: T+ (correct) vs T- (failures)
   |
   +-- Error analysts  (one per failure): "what went wrong? what rule prevents it?"
   +-- Success analysts (sampled):        "what pattern worked? reinforce it?"
   |
   v
Patch consolidator  (prevalence-weighted semantic union, conflict-resolved)
   |
   v
Evolved SKILL.md (version bumped)
```

There are two kinds of analyst, and that is deliberate. **Error analysts** read
the failures and ask what rule would have prevented each one. **Success analysts**
read the conversations that worked and ask what to reinforce. The first post
learned from failures only — every successful session was thrown away. But
successes are where the agent shows the patterns that already work, like which
casual phrasing ("vacation days") maps to which tool topic (PTO). Learning from
both is what produces a complete skill instead of a list of don'ts.

The other design choices that matter: analysts run **in parallel** and
**independently** (each sees one trajectory, no contamination); the consolidator
is **inductive** (keeps patterns that recur across many analysts, drops one-offs).
This follows two 2026 papers — [Trace2Skill](https://arxiv.org/abs/2603.25158)
(parallel analysts + inductive consolidation) and
[AutoSkill](https://arxiv.org/abs/2603.01145) (versioned skill evolution as a
semantic merge). More on what they taught us below. The engine is engine-only: it
consumes a report *dict* and returns skill text — it does not import
`quality_report`, so the two compose but stay independent.

## The demo: one agent, two tools, one realistic flaw

We keep the same example as the first post: a company-policy Q&A assistant
([`agent/agent.py`](agent/agent.py)) with a tool (`lookup_company_policy`) that
can look up every policy and benefit. Its V0 skill
([`skills/SKILL.v0.md`](skills/SKILL.v0.md)) is the one you saw there — a few
facts baked in, plus an anti-hallucination guardrail:

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
has. Ask "what's the 401k match?" and it says *"I do not have that information,
please contact HR"* — without ever calling the tool that knows the answer.

## The cycle: learning from users

The signal that drives evolution is **end-user conversations**. In production
these are the real sessions your agent already logs to BigQuery: every question a
user asked, every answer the agent gave, every time a user pushed back. The skill
evolves from that traffic. The agent learns what to fix and what to keep from how
users actually used it, not from a hand-written eval set.

The team that owns the agent provides exactly one thing: the answer key. We call
it the **golden Q&A** ([`eval/eval_spec.json`](eval/eval_spec.json)) — a set of
question/answer pairs you curate to define what a correct response looks like.
Everything else derives from it. The judge grades each conversation against it,
and the simulated user (below) is briefed with the same facts so it knows when the
agent is wrong. You never hand-write the traffic or the test cases. You state the
ground truth once, and the system generates the conversations and scores them
against it.

For the demo we don't have production users yet, so we simulate them. A user
simulator plays "Alex," a new employee who has memorized the golden-Q&A facts.
Alex asks questions the messy way real employees do (wrong assumptions, casual
phrasing, follow-ups), and when the agent gets a fact wrong, Alex pushes back
instead of accepting it:

```text
Agent: "The company matches 401k contributions at 6%."
Alex:  "My onboarding packet says the match is 4%, not 6%. Can you double-check?"
```

Every turn is tagged (correction, needs-specifics, out-of-scope, satisfied), so
each conversation carries explicit evidence of what was wrong and what the right
answer was. This is the same signal a real user produces when they correct your
agent, and it is what the analysts read to write the skill.

One command runs the whole cycle:

```bash
cd examples/skill_evolution_lab
./setup.sh YOUR_PROJECT_ID us-central1
./run_e2e_demo.sh
```

Deploy flawed V0 → simulate user conversations over an evolve set and a disjoint
held-out test set → score → run the evolution engine on the failures → deploy the
evolved V1 → re-score the held-out set → restore V0.

The engine reads the failing trajectories and writes a new skill. Because the
final merge step is stochastic — the same patches can consolidate into slightly
different skills run to run — it evolves a few candidates and keeps the
best-scoring one, and caps the skill's size to keep it honest. Here is the entire
skill it learned (abridged to its rules):

```text
You are a helpful company information assistant. Your primary function is to use
your available tools to answer employee questions about company policies.

Prioritize information retrieved from tools over the general knowledge below.
Always use your tools to find the most specific, up-to-date information.

## Anti-Patterns
- Do not rely on the static example list. Do not say you lack information just
  because a topic isn't listed above. Always try your tools first.
- Do not repeat high-level summaries. When asked for specifics (e.g. "what is the
  401k match?"), use your tools to find the exact detail, don't restate
  "competitive benefits".
- When a user corrects you or disputes an answer, do not just agree. Re-query your
  tools to verify the claim independently, then answer with what the tool returns.
```

It rediscovered two rules on its own. The first is to be tool-first. The second
is the one that matters most in a multi-turn conversation: when a user pushes
back, verify with a tool instead of just agreeing.

## Corrections are not answers: the anti-parroting rule

When Alex corrects the agent, the conversation can end two ways that both look
fine. The agent can re-query its tools, confirm the fact, and answer from the
tool. Or it can just say "you're right" and repeat what Alex said. The second is
**parroting**. The final message contains the right fact, so a naive scorer calls
it a success — but the agent verified nothing and the user did its job. In
production this is the failure that bites: the agent will "agree" with a confident
user even when the user is wrong.

The system is built so a parroted turn can never count as a win. It handles
parroting in two stages: first detect it, then learn from it.

- **Detection.** When a conversation is scored
  ([`scripts/quality_report.py`](../../scripts/quality_report.py) with
  `--tag-turns`), the turn tagger splits it at each correction and labels what the
  agent did next: `recovered` (it used a tool or cited a source), `parroted` (it
  only echoed the user's fact), or `not_recovered`. The rule is explicit: an
  answer counts as recovery *only* if the agent verified independently.
- **Learning.** A parroted turn is reclassified from success to failure
  (`_has_parroted_recovery` in
  [`scripts/skill_evolution.py`](../../scripts/skill_evolution.py)), so the engine
  can't reinforce it. The error analyst records the root cause as `PARROTING`
  ("echoed the user's correction without re-verifying via a tool"), and the
  success analyst refuses to extract a pattern from a parroted recovery
  ("NO_PATCH"). What comes back in the skill is the rule above: when corrected,
  verify with a tool, don't just agree.

This is the rule a plain "be tool-first" skill never reaches. Tool-first governs
the first answer. The anti-parroting rule governs what the agent does when a user
challenges it — which is exactly where an agent that learns from its users can
quietly teach itself to be a yes-man.

The lab exercises this directly with multi-turn cases
([`eval/questions_corrections.json`](eval/questions_corrections.json) to teach and
[`eval/questions_corrections_heldout.json`](eval/questions_corrections_heldout.json)
held-out), where the user asserts a wrong figure and the agent must re-verify.

## Results: V0 → V1 across three Gemini-3 models

Every number below is measured on a held-out set of questions the engine never saw
during evolution, so the gains reflect a general skill, not memorized fixes. We
track two separate things:

- **Correctness** — the share of answers that are factually right. An LLM judge
  grades each answer against the golden-Q&A answer key, so this is real accuracy,
  not a guess at "usefulness."
- **Grounding** — the share of answers where the agent actually called a tool,
  counted deterministically from the trace. This is a different axis from
  correctness: it tells you whether the agent *fetched* the fact instead of
  answering from memory or deferring to HR.

Each column shows the move from V0 (the flawed prompt) to V1 (the evolved skill),
as measured by this SDK example (see [`VERIFICATION.md`](VERIFICATION.md) for the
recorded run):

```text
Model                     Correctness     Grounding
                          V0  ->  V1      V0  ->  V1
-----------------------   -----------     -----------
gemini-3-flash-preview    23.8% -> 100%   29% -> 86%
gemini-3.1-flash-lite     14.3% -> 100%    0% -> 90%
gemini-3.1-pro-preview    19.0% -> 100%    5% -> 86%
```

Every model recovers to 100% on the held-out set, and none introduced a
hallucinated answer. The grounding column shows *why*: V0 barely calls the tool
(0–29% of answers), because the flawed skill tells it not to; V1 calls it on
~90%. The baseline is harsh because the held-out set is mostly benefits/expenses
topics that are not in V0's baked summary, so V0 declines on nearly all of them;
once the skill is tool-first, the same tool answers them. (A companion run on a
different question mix shows higher baselines — e.g. flash 61% → 83%, lite
67% → 89%, pro 44% → 94% — with the most capable model recovering the most; the
direction, a large grounded recovery, is the same.)

We show a single iteration (V0 → V1) here, but that is a choice for clarity, not a
limit. The framework is built to keep going: evolve a skill, deploy it, generate
fresh traffic, score, and evolve again — V1 → V2 → ... → VN. It runs this loop
agentically and decides when to stop on its own, on criteria like a quality
threshold or no further improvement between rounds, with a hard round cap as a
backstop. One round is enough to demonstrate the method; more rounds are a setting,
not a redesign.

## What it actually took (the traps)

Here is the part the polished demos skip. Almost everything below is a thing we
got wrong first.

### Trap 1: a bare prompt on a capable model has no headroom

Our first design used a *bare* prompt (just "you answer policy questions") on a
capable model with fully wired tools. It scored ~90% out of the box, because a
smart model just uses its tools. There was nothing for a skill to fix. The
"improvement" we measured was noise.

The fix is not a weaker model. It's a **real, correctable flaw** — a prompt that
systematically misbehaves in a way a better instruction can repair. The flawed
"contact HR" prompt above is that flaw. Without it, there is no demo.

### Trap 2: the architecture can forbid the behavior you're trying to teach

We didn't start with a single-agent demo. The original goal was a real
multi-agent system: a knowledge supervisor that coordinates specialist sub-agents
over A2A — a policy agent and an HR calculator, each a standalone service with its
own tools — and synthesizes their answers. The supervisor's whole job is to fan
out to the right specialists and merge what they return.

It kept failing, and no skill edit fixed it. The cause wasn't the prompt or the
model; it was the wiring. We'd attached the specialists with ADK's *handoff*
pattern (`sub_agents`), where a transfer **ends the turn** — so the supervisor
physically cannot call two specialists and merge their results. Switching to the
**AgentTool** pattern (each specialist is a tool the parent calls and gets a
result back from) unlocked it.

We later reused the flawed single-agent prompt from the first post to keep this
demo focused, but the architecture lesson stands: before you blame the prompt or
the model, check whether the architecture even *permits* the behavior you want.

### Trap 3: the most capable model fails the *most*

Counterintuitively, the stronger the model, the bigger the headroom from a flawed
prompt — because a stronger model follows the bad instruction more faithfully.
Gemini-3 Pro obeyed "answer only from the above, else contact HR" most strictly,
so it deferred on almost everything (one of the worst V0 baselines). And the
learned skill recovered it the most. The "crutch" intuition — that only weak
models need the skill — is backwards here.

### Trap 4: a judge without ground truth lies — anchor it to golden answers

This one nearly shipped. An LLM judge that scores "usefulness / grounding"
*without ground truth* mislabeled correct, tool-grounded answers as ungrounded
and unhelpful — worst on the most capable model, whose answers are the most
verbose. By that no-ground-truth judge, Pro V1 scored around **50%**. But every
one of those answers had called a tool and was factually right; the real number
was far higher.

The fix isn't to throw out the judge — it's to **give it the answer key**. Our
analytics SDK has a golden-Q&A eval-spec ([`eval/eval_spec.json`](eval/eval_spec.json)):
you supply `{question, expected_answer}` pairs, and the judge grades each response
against the expected answer instead of guessing
(`golden_eval_summary.matched_meaningful_rate`). The lesson: an LLM judge is only
as trustworthy as the ground truth you give it — measure against expected answers,
and treat any no-ground-truth "quality score" as an estimate, not a result.

### Trap 5: overfitting shows up as bloat

When we ran evolution against a task with no real general fix (Trap 1), the
algorithm didn't fail loudly — it overfit quietly, producing 12KB skills full of
**keyword-mapping tables** ("travel, meals → expenses"). A skill that enumerates
cases instead of stating a rule is the tell-tale sign you're optimizing the judge,
not teaching the agent. A good extracted skill is small enough to read and
believe (ours is ~2KB; `--max-chars` keeps it honest).

### What the papers had already paid for

Three of our bugs were named and solved in the source papers:

- **Held-out validation.** We first measured improvement on the same questions the
  patches were written from — textbook overfitting. Trace2Skill (§2.1) insists
  `D_evolve` and `D_test` be disjoint. We split them; every headline number above
  is on a held-out set.
- **Sequential drift.** Re-evolving from the already-evolved skill round after
  round made quality collapse — a consolidation would drop a rule a prior round
  learned. Trace2Skill (§4.1): parallel consolidation from a frozen base beats
  sequential re-editing. We added a round cap and stop-on-no-improvement.
- **Rewrite-from-scratch content loss.** Our consolidator rewrote the whole skill
  each time, silently dropping rules. AutoSkill's merge operator (`P_merge`,
  §3.4.3) prescribes a *semantic union*: keep every existing check unless a patch
  overrides it. We added a diff-guard that rejects any candidate dropping a
  section. The collapses stopped.

## Closing the loop: fix what you can, route what you can't

A skill can only fix *behavior*. It cannot invent a fact the tools don't have or
build a capability that doesn't exist — and pretending otherwise is how demos
overstate themselves. The honest, more useful framing is: evolution heals what a
skill can fix, and for the rest it hands you an attributed, owner-routed backlog.
A triage pass classifies every remaining failure by *who* can fix it:

- **EVOLUTION** — had the tool and data but misbehaved → a skill edit fixes it.
- **ENG** — a tool returned a wrong value, or no tool exists → build/fix the tool.
- **KNOWLEDGE** — the right tool ran, but the fact isn't in the data → add the doc.
- **PRODUCT** — out of scope → a clean decline is a policy decision.

In an earlier multi-agent run this produced a pull request for the skill fix plus
GitHub issues for the rest — each labeled and routed:

```text
PR     evolved skill (reviewable diff, before/after metrics)
issue  [ENG]        incident-response question -- no tool exists
issue  [KNOWLEDGE]  marriage as a qualifying life event -- fact missing
issue  [PRODUCT]    "list everything that resets at year end" -- decline
```

That's the difference between a quality *score* and a quality *loop*: the agent
fixes what it can, proves it with a diff, and tells you — with an owner and a
recommended action — what it cannot.

> **Note — scope.** The triage/routing system above (the PR + labeled-issue
> backlog) is a **separate story and demo**; it is **not part of this example or
> the SDK** yet. This post is scoped to the self-contained skill loop — flawed V0
> → evolved V1, grounded and versioned. We recommend pairing it with a triage
> pass in production, and we'll cover that end-to-end on its own.

## From the demo to production: the loop runs on real traffic

The demo simulates users because we are starting from zero. In production you
don't have to. Your agent already logs every real conversation to BigQuery, and
that is the traffic the loop runs on. The engine is the same; the only thing that
changes is where the conversations come from.

Two agents keep it going:

- **A quality agent, daily.** It scores recent real sessions against the same
  golden Q&A ground truth, filtered to the deployed skill version. Answers that
  used to work but now fail are a regression. A known topic handled poorly is a
  gap. A question nobody anticipated is a new topic for a human to rule in or out.
- **An evolution agent, weekly (or when gaps pile up).** It pulls the real
  sessions for the current skill version, runs the same analyst fleet and
  consolidation, and opens a PR with the evolved `SKILL.md` and a before/after
  quality table. A human reviews the diff, the eval gate runs, and the merge
  redeploys the agent.

Simulated users while you bootstrap, real users once you ship. Either way the
skill keeps learning from how users actually use the agent.

## How this relates to the research

[Trace2Skill](https://arxiv.org/abs/2603.25158) (Alibaba/Qwen, 2026) distills
trajectories into skills via parallel analysts and inductive consolidation; we
adopt its frozen-base consolidation, content-preserving guardrails, and held-out
split. [AutoSkill](https://arxiv.org/abs/2603.01145) (ECNU/Shanghai AI Lab, 2026)
frames lifelong skill evolution as a versioned semantic merge; we adopt its
`P_merge` operator. We differ in scale (one comprehensive, legible skill rather
than a large reference tree) and in packaging: a runnable loop that learns from
user conversations, a readable skill instead of a flat prompt, ground-truth
scoring so the numbers hold up, Skill Registry versioning, and a triage pass that
routes what a skill can't fix.

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
skill, re-scores a held-out set, and restores V0 — printing the V0 → V1 numbers.

## The takeaway

The first post fixed an agent's failures with a teacher model and a prompt
optimizer. This post removes the teacher. The agent reads its own user
conversations, learns from the ones that worked and the ones that didn't, and
writes itself a structured skill you can read and version. Run it on three
Gemini-3 models and every one improves — from harsh, tool-suppressed baselines
all the way to a fully grounded skill.

A skill only fixes behavior, so the loop is also honest about what a new rule
can't touch: a missing tool, a missing fact, an out-of-scope request, each routed
to whoever can fix it. In the demo the conversations are simulated; in production
they are real. Either way, the agent turns real usage into a better version of
itself.
