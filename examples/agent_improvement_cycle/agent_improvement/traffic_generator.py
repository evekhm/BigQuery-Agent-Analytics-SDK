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

"""Traffic generation for the improvement cycle."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
import json

from google import genai
from google.genai.types import GenerateContentConfig
from google.genai.types import HttpOptions
from google.genai.types import HttpRetryOptions


class TrafficGenerator(ABC):
  """Abstract interface for generating synthetic traffic."""

  @abstractmethod
  def generate(
      self,
      count: int,
      existing_questions: list[str],
      tool_info: list[dict],
  ) -> list[dict]:
    """Generate synthetic eval cases.

    Args:
        count: Number of cases to generate.
        existing_questions: Questions to avoid duplicating.
        tool_info: Tool signature dicts from
            :func:`tool_introspection.extract_tool_signatures`.

    Returns:
        List of eval case dicts with ``id``, ``question``, and
        ``category`` keys.
    """


_GENERIC_TRAFFIC_PROMPT = """You are generating realistic user questions for an AI agent.

The agent has these tools available:
{tool_descriptions}

## Rules
1. ONLY ask questions that the tools above can answer.
2. Mix direct factual questions with situational ones.
3. Cover all available tools. Vary the phrasing naturally.

## Existing questions to AVOID duplicating
{existing_questions}

Generate exactly {count} questions.

Return JSON with exactly this structure:
{{
  "traffic_cases": [
    {{
      "id": "traffic_<short_descriptive_id>",
      "question": "the user's question",
      "category": "the relevant tool/topic"
    }}
  ]
}}

Return ONLY the JSON, no other text.
"""


class GenericTrafficGenerator(TrafficGenerator):
  """Generates traffic from tool descriptions using Gemini.

  Works with any agent by introspecting its tool signatures.
  """

  def __init__(self, model_id: str = "gemini-2.5-flash") -> None:
    self._model_id = model_id
    self._client = genai.Client(
        http_options=HttpOptions(
            retry_options=HttpRetryOptions(
                attempts=3,
                initial_delay=10.0,
                http_status_codes=[429],
            )
        )
    )

  def generate(
      self,
      count: int,
      existing_questions: list[str],
      tool_info: list[dict],
  ) -> list[dict]:
    tool_desc = "\n".join(
        f"- {t['signature']}: {t['description'].split(chr(10))[0]}"
        for t in tool_info
    )
    existing_fmt = "\n".join(f"- {q}" for q in existing_questions) or "(none)"

    prompt = _GENERIC_TRAFFIC_PROMPT.format(
        tool_descriptions=tool_desc,
        existing_questions=existing_fmt,
        count=count,
    )

    response = self._client.models.generate_content(
        model=self._model_id,
        contents=prompt,
        config=GenerateContentConfig(
            temperature=0.8,
            response_mime_type="application/json",
        ),
    )

    result = json.loads(response.text)
    return result.get("traffic_cases", [])
