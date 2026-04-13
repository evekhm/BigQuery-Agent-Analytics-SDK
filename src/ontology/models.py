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

"""Pydantic models for the v0 ontology spec."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

# Free-form annotation values: a string or a list of strings.
AnnotationValue = Union[str, list[str]]


class PropertyType(str, Enum):
  """Semantic property types.

  Map to GoogleSQL types shared by BigQuery and Spanner. Backend-specific
  unsupported combinations are deferred to binding/compile time.
  """

  STRING = "string"
  BYTES = "bytes"
  INTEGER = "integer"
  DOUBLE = "double"
  NUMERIC = "numeric"
  BOOLEAN = "boolean"
  DATE = "date"
  TIME = "time"
  DATETIME = "datetime"
  TIMESTAMP = "timestamp"
  JSON = "json"


class Cardinality(str, Enum):
  """Relationship cardinality."""

  ONE_TO_ONE = "one_to_one"
  ONE_TO_MANY = "one_to_many"
  MANY_TO_ONE = "many_to_one"
  MANY_TO_MANY = "many_to_many"


class Property(BaseModel):
  """A property of an entity or relationship."""

  model_config = ConfigDict(extra="forbid")

  name: str
  type: PropertyType
  expr: Optional[str] = None
  description: Optional[str] = None
  synonyms: Optional[list[str]] = None
  annotations: Optional[dict[str, AnnotationValue]] = None


class Keys(BaseModel):
  """Key specification for entities and relationships.

  - On entities: ``primary`` is required; ``additional`` is forbidden.
  - On relationships: ``primary`` XOR ``additional``; both omitted is
    legal (multi-edges permitted). ``alternate`` only applies with
    ``primary``.

  Cross-context rules are enforced in the loader; this model only
  captures shape.
  """

  model_config = ConfigDict(extra="forbid")

  # ``min_length=1`` rejects ``primary: []`` / ``additional: []`` /
  # ``alternate: []`` at parse time so the loader never has to interpret
  # an empty list as "no key declared".
  primary: Optional[list[str]] = Field(default=None, min_length=1)
  alternate: Optional[list[list[str]]] = Field(default=None, min_length=1)
  additional: Optional[list[str]] = Field(default=None, min_length=1)


class Entity(BaseModel):
  """Entity (node type) definition."""

  model_config = ConfigDict(extra="forbid")

  name: str
  extends: Optional[str] = None
  # Optional at the model level: a child entity inherits its parent's keys
  # and is forbidden from redeclaring them. The loader enforces that
  # every entity has effective ``keys.primary``.
  keys: Optional[Keys] = None
  properties: list[Property] = Field(default_factory=list)
  description: Optional[str] = None
  synonyms: Optional[list[str]] = None
  annotations: Optional[dict[str, AnnotationValue]] = None


class Relationship(BaseModel):
  """Relationship (edge type) definition."""

  model_config = ConfigDict(extra="forbid", populate_by_name=True)

  name: str
  extends: Optional[str] = None
  keys: Optional[Keys] = None
  from_: str = Field(alias="from")
  to: str
  cardinality: Optional[Cardinality] = None
  properties: list[Property] = Field(default_factory=list)
  description: Optional[str] = None
  synonyms: Optional[list[str]] = None
  annotations: Optional[dict[str, AnnotationValue]] = None


class Ontology(BaseModel):
  """Top-level ontology document."""

  # ``coerce_numbers_to_str`` lets users write ``version: 0.1`` (which
  # YAML parses as a float) without quoting.
  model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

  ontology: str
  version: Optional[str] = None
  entities: list[Entity] = Field(min_length=1)
  relationships: list[Relationship] = Field(default_factory=list)
  description: Optional[str] = None
  synonyms: Optional[list[str]] = None
  annotations: Optional[dict[str, AnnotationValue]] = None
