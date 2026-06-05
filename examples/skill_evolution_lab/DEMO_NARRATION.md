# Your Agent Can Write Its Own Skill

This example shows an agent that reads its own conversation traces — successes
and failures — and extracts a structured, versioned **skill**. No teacher
model, no managed prompt optimizer. The agent learns what to fix and what to
keep from how it was actually used.

## What is a skill?

A skill is a structured markdown document (`SKILL.md`): YAML frontmatter for
versioning, a markdown body for instructions. Because it's plain, versioned
markdown, an evolved skill is a **reviewable diff** with named sections
(knowledge, response rules, anti-patterns) — you can read each rule the agent
learned and see exactly what changed between versions. Google's
[ADK](https://adk.dev) and the Gemini Enterprise Agent Platform **Skill
Registry** treat skills as a first-class, versioned concept; here V0 is the
registry's first revision and the evolved V1 is the second.

## The evolution engine

The engine (`scripts/skill_evolution.py` in this SDK, imported by
`analyze_and_evolve.py` — not copied) takes scored conversations in and produces
an evolved skill out:

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
drops one-offs). This follows two 2026 papers —
[Trace2Skill](https://arxiv.org/abs/2603.25158) (parallel analysts + inductive
consolidation) and [AutoSkill](https://arxiv.org/abs/2603.01145) (versioned
skill evolution as a semantic merge).

## The demo: one agent, two tools, one realistic flaw

A company-policy Q&A assistant (`agent/agent.py`) with a tool
(`lookup_company_policy`) that can look up **every** policy and benefit. Its V0
skill (`skills/SKILL.v0.md`) bakes in a few facts plus an anti-hallucination
guardrail:

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
answer ($75/day meals, 4% 401k match, $1,500 family HSA, ...).

The point: the tool already returns the right answers. Only the skill is wrong.
The model, tools, and questions stay fixed across V0 and V1 — **only the skill
file changes** — so any quality delta is attributable to the skill.

## The cycle

```bash
./setup.sh YOUR_PROJECT_ID us-central1
./run_e2e_demo.sh
```

Deploy flawed V0 → run questions over an evolve set and a disjoint held-out test
set → score against the golden Q&A answer key → run the evolution engine on the
failures → deploy the evolved V1 → re-score the held-out set → restore V0.

The engine reads the failing trajectories and writes a new, small, tool-first
skill (size-capped to stay honest). It typically rediscovers two rules on its
own: **be tool-first**, and — the one that matters most in multi-turn — **when a
user pushes back, verify with a tool instead of just agreeing.**

## <a name="anti-parroting"></a>Corrections are not answers: the anti-parroting rule

When a user corrects the agent, the conversation can end two ways that both look
fine. The agent can re-query its tool, confirm the fact, and answer from the
tool. Or it can just say "you're right" and repeat what the user said. The
second is **parroting**: the final message contains the right fact, so a naive
scorer calls it a success — but the agent verified nothing. In production this is
the failure that bites: the agent becomes a yes-man to a confident, wrong user.

The lab exercises this directly. `eval/questions_corrections.json` and
`eval/questions_corrections_heldout.json` are multi-turn cases where the user
asserts a *wrong* figure ("the 401k match is 6%, right?"). The flawed V0, with
no fact to stand on, declines or caves; the evolved V1 re-verifies with the tool
and holds the correct value (4%).

It is a **detect-then-learn** pipeline, and both halves live in this SDK:

- **Detection** — `scripts/quality_report.py`, the `_TURN_TAGGER_PROMPT`. It
  splits a conversation at each correction and labels what the agent did next:
  `recovered` (used a tool / cited a source), `parroted` (only echoed the user's
  fact), or `not_recovered`. An answer counts as recovery *only* if the agent
  verified independently.
- **Learning** — `scripts/skill_evolution.py`. A parroted turn is reclassified
  from success to failure (`_has_parroted_recovery`), so the engine can't
  reinforce it. The error analyst records the root cause `PARROTING`
  ("echoed the user's correction without re-verifying via a tool"), and the
  success analyst refuses to extract a pattern from a parroted recovery
  (`NO_PATCH`). What comes back in the skill is the rule: when corrected, verify
  with a tool, don't just agree.

`compare_runs.py` reports the corrections as their own line and counts parroted
sub-trajectories before and after evolution.

## Results

See [`VERIFICATION.md`](VERIFICATION.md) for a recorded end-to-end run of this
example (V0 → V1 on the held-out set, single-turn and anti-parroting).

For reference, the published blog ran the same loop across three Gemini-3
models. Correctness is graded against the known answer (LLM judge anchored on
ground truth); grounding is the share of answers that actually called a tool:

```text
Model                    V0 correct   V1 correct    grounding V0 -> V1
----------------------   ----------   ----------    ------------------
gemini-3-flash-preview      61%          83%             94% -> 100%
gemini-3.1-flash-lite       67%          89%             67% ->  89%
gemini-3.1-pro-preview      44%          94%             61% -> 100%
```

Every model improves, with zero hallucinated answers introduced — the most
capable model (Pro) most of all, because it followed the bad instruction most
faithfully and so had the most headroom to recover.

## Traps worth knowing

- **A bare prompt on a capable model has no headroom.** A smart model with wired
  tools just works (~90% out of the box) — there is nothing for a skill to fix.
  You need a *real, correctable flaw* (the "contact HR" prompt above), not a
  weaker model.
- **The most capable model fails the most.** A stronger model follows the bad
  instruction more faithfully, so it defers on almost everything (the worst V0)
  and the learned skill recovers it the most. The "only weak models need the
  skill" intuition is backwards.
- **A judge without ground truth lies.** A "usefulness" judge with no answer key
  mislabels correct, tool-grounded answers — worst on the most verbose (most
  capable) model. The fix is `eval/eval_spec.json`: grade each response against
  the expected answer (`golden_eval_summary.matched_meaningful_rate`), and treat
  any no-ground-truth score as an estimate.
- **Overfitting shows up as bloat.** A skill that enumerates keyword-mapping
  cases instead of stating a rule is the tell-tale sign you're optimizing the
  judge, not teaching the agent. A good extracted skill is small enough to read
  and believe (`--max-chars` keeps it honest).

## How this relates to the research

[Trace2Skill](https://arxiv.org/abs/2603.25158) (parallel analysts + inductive
consolidation) contributes the frozen-base consolidation, content-preserving
guardrails, and held-out split; [AutoSkill](https://arxiv.org/abs/2603.01145)
contributes the versioned semantic-merge (`P_merge`) operator. This example
differs in packaging: a runnable loop that learns from conversations, a readable
versioned skill instead of a flat prompt, ground-truth scoring so the numbers
hold up, and Skill Registry versioning.
