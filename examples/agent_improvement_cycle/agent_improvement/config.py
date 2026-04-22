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

"""Configuration for the agent improvement cycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
  from agent_improvement.prompt_adapter import PromptAdapter
  from agent_improvement.traffic_generator import TrafficGenerator
  from google.adk.agents import Agent


@dataclass
class ImprovementConfig:
  """Everything needed to run an improvement cycle on any ADK agent.

  Args:
      agent_factory: A callable that takes a prompt string and returns a
          fully configured ADK Agent.  Called each time a candidate
          prompt needs to be evaluated.
      agent_name: Human-readable name for the agent (used in logs).
      agent_tools: The tool functions the target agent uses.  Used by
          :func:`tool_introspection.extract_tool_signatures` to inject
          tool documentation into the improver prompt.
      prompt_adapter: Reads and writes the agent's prompt storage
          (e.g. a ``prompts.py`` file).
      eval_cases_path: Path to the golden eval set JSON file.
      traffic_generator: Optional traffic generator for full-cycle mode.
          If *None*, only golden-eval improvement is run.
      model_id: Gemini model used by the improver and judge LLMs.
      max_attempts: Maximum number of candidate prompts to try before
          giving up.
      quality_threshold: Fraction of golden cases that must pass
          (1.0 = all cases).
  """

  agent_factory: Callable[[str], Agent]
  agent_name: str
  agent_tools: list[Callable]
  prompt_adapter: PromptAdapter
  eval_cases_path: str
  traffic_generator: TrafficGenerator | None = None
  model_id: str = "gemini-2.5-flash"
  max_attempts: int = 3
  quality_threshold: float = 1.0
