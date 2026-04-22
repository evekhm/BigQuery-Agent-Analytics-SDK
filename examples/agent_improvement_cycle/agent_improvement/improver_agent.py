# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""LoopAgent-based prompt improver.

Creates a LoopAgent wrapping a single LlmAgent that has tools to:
1. Read the quality report and current prompt
2. Generate a candidate improved prompt via Gemini
3. Test the candidate against the golden eval set
4. Write the validated prompt and exit the loop

The loop exits when all golden cases pass, or after ``max_iterations``.
"""

from __future__ import annotations

import asyncio
import json
import re

from agent_improvement.config import ImprovementConfig
from agent_improvement.eval_runner import EvalRunner
from agent_improvement.prompts import IMPROVER_PROMPT
from agent_improvement.tool_introspection import format_tool_signatures
from google import genai
from google.adk.agents import Agent
from google.adk.agents import LoopAgent
from google.adk.models import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import exit_loop
from google.genai import types
from google.genai.types import Content
from google.genai.types import GenerateContentConfig
from google.genai.types import HttpOptions
from google.genai.types import HttpRetryOptions
from google.genai.types import Part

# ---------------------------------------------------------------------------
# Shared state — set by run_improvement(), read by tool functions
# ---------------------------------------------------------------------------

_state: dict = {}


# ---------------------------------------------------------------------------
# Tool functions for the inner LlmAgent
# ---------------------------------------------------------------------------


def read_quality_report() -> str:
  """Read the quality report that triggered this improvement cycle.

  Returns a JSON summary of problem sessions including questions,
  responses, and usefulness scores.
  """
  report = _state.get("report", {})
  summary = report.get("summary", {})

  problem_sessions = []
  for session in report.get("sessions", []):
    metrics = session.get("metrics", {})
    usefulness = metrics.get("response_usefulness", {})
    cat = usefulness.get("category", "unknown")
    if cat not in ("unhelpful", "partial"):
      continue
    problem_sessions.append(
        {
            "question": session.get("question", "?"),
            "response": session.get("response", "")[:300],
            "usefulness": cat,
            "justification": usefulness.get("justification", ""),
        }
    )

  return json.dumps(
      {
          "summary": summary,
          "problem_sessions": problem_sessions,
      },
      indent=2,
  )


def read_current_prompt() -> str:
  """Read the current agent prompt and version.

  Returns JSON with the prompt text, version number, and available
  tool signatures.
  """
  config: ImprovementConfig = _state["config"]
  prompt_text, version = config.prompt_adapter.read_prompt()
  tool_sigs = format_tool_signatures(config.agent_tools)
  return json.dumps(
      {
          "version": version,
          "prompt": prompt_text,
          "tool_signatures": tool_sigs,
      },
      indent=2,
  )


def generate_candidate(current_prompt: str, current_version: int) -> str:
  """Generate an improved prompt candidate using Gemini.

  Args:
      current_prompt: The current agent prompt text.
      current_version: The current prompt version number.

  Returns:
      JSON with ``improved_prompt`` and ``changes_summary`` fields.
  """
  config: ImprovementConfig = _state["config"]
  report = _state.get("report", {})
  summary = report.get("summary", {})

  # Format problem sessions
  lines = []
  for session in report.get("sessions", []):
    metrics = session.get("metrics", {})
    usefulness = metrics.get("response_usefulness", {})
    cat = usefulness.get("category", "unknown")
    if cat not in ("unhelpful", "partial"):
      continue
    lines.append(f"- Question: {session.get('question', '?')}")
    resp = session.get("response", "")[:300]
    lines.append(f"  Response: {resp}")
    lines.append(f"  Usefulness: {cat}")
    lines.append("")

  problem_text = "\n".join(lines) or "No problem sessions found."
  tool_sigs = format_tool_signatures(config.agent_tools)

  prompt = IMPROVER_PROMPT.format(
      current_version=current_version,
      current_prompt=current_prompt,
      total_sessions=summary.get("total_sessions", 0),
      meaningful=summary.get("meaningful", 0),
      meaningful_rate=summary.get("meaningful_rate", 0),
      partial=summary.get("partial", 0),
      unhelpful=summary.get("unhelpful", 0),
      unhelpful_rate=summary.get("unhelpful_rate", 0),
      problem_sessions=problem_text,
      tool_signatures=tool_sigs,
  )

  client = genai.Client(
      http_options=HttpOptions(
          retry_options=HttpRetryOptions(
              attempts=3,
              initial_delay=10.0,
              http_status_codes=[429],
          )
      )
  )
  response = client.models.generate_content(
      model=config.model_id,
      contents=prompt,
      config=GenerateContentConfig(
          temperature=0.2,
          response_mime_type="application/json",
      ),
  )
  return response.text


async def test_candidate(candidate_prompt: str) -> str:
  """Test a candidate prompt against the golden eval set.

  Args:
      candidate_prompt: The full text of the candidate prompt.

  Returns:
      JSON with ``all_passed``, ``passed``, ``total``, and per-case
      results.
  """
  config: ImprovementConfig = _state["config"]
  eval_runner = EvalRunner(
      agent_factory=config.agent_factory,
      model_id=config.model_id,
  )
  all_passed, passed, total, results = await eval_runner.run_golden_eval(
      candidate_prompt, config.eval_cases_path
  )
  return json.dumps(
      {
          "all_passed": all_passed,
          "passed": passed,
          "total": total,
          "results": [
              {
                  "case_id": r["case_id"],
                  "pass": r.get("pass", False),
                  "reason": r.get("reason", ""),
              }
              for r in results
          ],
      },
      indent=2,
  )


def write_prompt(candidate_prompt: str, changes_summary: str) -> str:
  """Write a validated candidate prompt to storage.

  Only call this AFTER test_candidate returns all_passed=true.

  Args:
      candidate_prompt: The full text of the improved prompt.
      changes_summary: Brief description of what changed.

  Returns:
      Confirmation message with the new version number.
  """
  config: ImprovementConfig = _state["config"]
  _, current_version = config.prompt_adapter.read_prompt()
  new_version = config.prompt_adapter.write_prompt(
      candidate_prompt, current_version, changes_summary
  )
  return f"Written PROMPT_V{new_version}. Changes: {changes_summary}"


# ---------------------------------------------------------------------------
# Failure extraction helpers
# ---------------------------------------------------------------------------

_REQUIRED_CASE_KEYS = {"id", "question", "category", "expected_tool"}


def extract_failed_cases(report: dict) -> list[dict]:
  """Extract failed sessions as new golden eval cases."""
  new_cases = []
  for session in report.get("sessions", []):
    cat = (
        session.get("metrics", {})
        .get("response_usefulness", {})
        .get("category", "")
    )
    if cat not in ("unhelpful", "partial"):
      continue

    question = session.get("question", "")
    if not question:
      continue

    case_id = re.sub(r"[^a-z0-9]+", "_", question.lower().strip())[:40]
    case_id = f"extracted_{case_id.strip('_')}"

    new_cases.append(
        {
            "id": case_id,
            "question": question,
            "category": "unknown",
            "expected_tool": "lookup_company_policy",
            "notes": f"Extracted from failed synthetic traffic ({cat})",
        }
    )
  return new_cases


def add_eval_cases(eval_cases_path: str, new_cases: list[dict]) -> int:
  """Append new eval cases to the golden eval set."""
  with open(eval_cases_path) as f:
    data = json.load(f)

  existing_ids = {c["id"] for c in data["eval_cases"]}
  existing_questions = {c["question"] for c in data["eval_cases"]}

  added = 0
  for case in new_cases:
    missing = _REQUIRED_CASE_KEYS - set(case.keys())
    if missing:
      print(f"  Skipping invalid eval case (missing {missing}): {case}")
      continue
    if case["id"] in existing_ids or case["question"] in existing_questions:
      continue
    data["eval_cases"].append(case)
    existing_ids.add(case["id"])
    existing_questions.add(case["question"])
    added += 1

  with open(eval_cases_path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

  return added


def build_report_from_eval_results(eval_results_path: str) -> dict:
  """Build a synthetic quality report from golden eval results JSON.

  Bridges the gap between ``run_eval.py --golden`` output format and
  the quality report format the improver expects.
  """
  with open(eval_results_path) as f:
    results = json.load(f)

  total = len(results)
  passed = sum(1 for r in results if r.get("pass", False))
  failed = total - passed

  sessions = []
  for r in results:
    is_pass = r.get("pass", False)
    sessions.append(
        {
            "session_id": r.get("session_id", r.get("case_id", "?")),
            "question": r.get("question", ""),
            "response": r.get("response", ""),
            "metrics": {
                "response_usefulness": {
                    "category": ("meaningful" if is_pass else "unhelpful"),
                    "justification": r.get("reason", ""),
                },
                "task_grounding": {
                    "category": ("grounded" if is_pass else "ungrounded"),
                    "justification": "",
                },
            },
        }
    )

  return {
      "summary": {
          "total_sessions": total,
          "meaningful": passed,
          "meaningful_rate": (round(100 * passed / total) if total else 0),
          "partial": 0,
          "unhelpful": failed,
          "unhelpful_rate": (round(100 * failed / total) if total else 0),
      },
      "sessions": sessions,
  }


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

_PROMPT_ENGINEER_INSTRUCTION = """You are a prompt engineer improving an ADK agent's system prompt.

Your goal: make ALL golden eval cases pass by rewriting the prompt.

## Workflow (repeat until all cases pass or you run out of attempts)

1. Call `read_quality_report` to understand what went wrong.
2. Call `read_current_prompt` to see the current prompt and available tools.
3. Call `generate_candidate` with the current prompt and version.
   Parse the JSON result to extract `improved_prompt` and `changes_summary`.
4. Call `test_candidate` with the `improved_prompt` text.
5. If `all_passed` is true:
   a. Call `write_prompt` with the candidate and summary.
   b. Call `exit_loop` to finish.
6. If `all_passed` is false:
   Review which cases failed and try again from step 3 with
   adjustments.

IMPORTANT:
- Always test before writing. Never write an untested candidate.
- If a candidate fails, analyze WHY before generating the next one.
- When calling `generate_candidate`, pass the current prompt TEXT
  and version NUMBER as separate arguments.
"""


def create_improver_agent(
    config: ImprovementConfig,
) -> LoopAgent:
  """Create the LoopAgent that improves the target agent's prompt.

  Args:
      config: Improvement configuration including agent factory,
          tools, prompt adapter, and eval cases path.

  Returns:
      A configured LoopAgent ready to run.
  """
  inner_agent = Agent(
      name="prompt_engineer",
      model=Gemini(
          model=config.model_id,
          retry_options=types.HttpRetryOptions(attempts=3),
      ),
      description="Improves an agent's prompt to pass all eval cases.",
      instruction=_PROMPT_ENGINEER_INSTRUCTION,
      tools=[
          read_quality_report,
          read_current_prompt,
          generate_candidate,
          test_candidate,
          write_prompt,
          exit_loop,
      ],
      output_key="improvement_result",
  )

  return LoopAgent(
      name="prompt_improver",
      sub_agents=[inner_agent],
      max_iterations=config.max_attempts,
  )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_improvement(
    config: ImprovementConfig,
    report: dict | None = None,
    report_path: str | None = None,
    from_eval_results: bool = False,
) -> dict:
  """Run the improvement cycle.

  Args:
      config: Improvement configuration.
      report: Pre-loaded quality report dict. Mutually exclusive with
          ``report_path``.
      report_path: Path to quality report JSON (or eval results JSON
          if ``from_eval_results`` is True).
      from_eval_results: If True, treat ``report_path`` as golden eval
          results and build a synthetic quality report.

  Returns:
      Dict with ``old_version``, ``new_version``, ``golden_cases``,
      and ``improvement_result`` keys.
  """
  # Load report
  if report is None:
    if report_path is None:
      raise ValueError("Either report or report_path is required")
    if from_eval_results:
      report = build_report_from_eval_results(report_path)
    else:
      with open(report_path) as f:
        report = json.load(f)

  _, old_version = config.prompt_adapter.read_prompt()
  print(f"\n=== Agent Improver ===\n")
  print(f"  Current prompt version: v{old_version}")
  print(
      f"  Quality score:" f" {report['summary']['meaningful_rate']}% meaningful"
  )

  if report["summary"].get("total_sessions", 0) == 0:
    print("  ERROR: Report has 0 sessions. Cannot improve.")
    return {
        "old_version": old_version,
        "new_version": old_version,
        "golden_cases": 0,
        "improvement_result": "no_data",
    }

  if report["summary"]["meaningful_rate"] >= 95:
    print("  Quality is already high (>=95%). No improvement needed.")
    return {
        "old_version": old_version,
        "new_version": old_version,
        "golden_cases": 0,
        "improvement_result": "already_good",
    }

  # Extract failed cases into golden set FIRST
  failed_cases = extract_failed_cases(report)
  if failed_cases:
    added = add_eval_cases(config.eval_cases_path, failed_cases)
    with open(config.eval_cases_path) as f:
      golden_count = len(json.load(f).get("eval_cases", []))
    print(
        f"  Extracted {len(failed_cases)} failed cases, added"
        f" {added} new to golden set ({golden_count} total)."
    )
  else:
    print("  No failed cases to extract.")

  # Set shared state for tool functions
  _state["config"] = config
  _state["report"] = report

  # Run the LoopAgent
  improver = create_improver_agent(config)
  runner = InMemoryRunner(agent=improver, app_name="prompt_improver")
  session = await runner.session_service.create_session(
      app_name="prompt_improver",
      user_id="improver",
  )

  user_message = Content(
      role="user",
      parts=[
          Part(
              text=(
                  "Improve the agent's prompt so all golden eval cases"
                  " pass. Start by reading the quality report."
              )
          )
      ],
  )

  result_text = ""
  async for event in runner.run_async(
      user_id="improver",
      session_id=session.id,
      new_message=user_message,
  ):
    if event.content and event.content.parts:
      for part in event.content.parts:
        if part.text:
          result_text += part.text

  # Read final state
  _, new_version = config.prompt_adapter.read_prompt()
  with open(config.eval_cases_path) as f:
    golden_count = len(json.load(f).get("eval_cases", []))

  if new_version > old_version:
    print(f"\n  v{old_version} -> v{new_version} complete.")
  else:
    print(
        "\n  WARNING: No improvement was written. All candidates"
        " may have failed regression tests."
    )

  return {
      "old_version": old_version,
      "new_version": new_version,
      "golden_cases": golden_count,
      "improvement_result": result_text,
  }
