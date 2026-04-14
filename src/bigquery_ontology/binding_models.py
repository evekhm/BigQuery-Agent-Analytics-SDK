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

"""Pydantic models for binding YAML.

A binding document attaches a logical ontology (see ``ontology_models``)
to physical tables and columns on a specific backend. One file describes
one deployment target; it says *where* the data lives and never *how* it
is transformed.

These models capture shape only: required fields, enum membership,
unknown-key rejection, and list min-length constraints. Anything that
needs to consult the referenced ontology — checking that every
non-derived property is bound, that derived properties are *not* bound,
that relationship endpoint arities match the endpoint entity's primary
key, that bound types are representable on the target backend — belongs
to the binding loader, not here.

Only the BigQuery target is modeled today. Spanner lands alongside the
SDK's Spanner support.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class Backend(str, Enum):
  """Backend identifier carried by the ``target`` block.

  Kept as a single-member enum rather than a literal so the YAML-level
  error message on an unsupported backend reads like any other enum
  mismatch, and so adding Spanner later is a one-line change here
  instead of a type swap at every call site.
  """

  BIGQUERY = "bigquery"


class BigQueryTarget(BaseModel):
  """Where the bound tables live on BigQuery.

  ``project`` and ``dataset`` double as (1) the physical location of the
  target dataset and (2) the defaults used to resolve bare ``table`` or
  ``dataset.table`` source names in each entity/relationship binding. A
  fully-qualified ``project.dataset.table`` source overrides both.
  """

  model_config = ConfigDict(extra="forbid")

  backend: Backend
  project: str
  dataset: str


class PropertyBinding(BaseModel):
  """Maps one ontology property to one physical column.

  ``name`` must name a property declared on the enclosing entity or
  relationship in the referenced ontology (inherited properties count);
  ``column`` is the physical column in that binding's ``source``. Type
  compatibility is not checked here — the physical column type must
  already match the ontology property type, upstream.
  """

  model_config = ConfigDict(extra="forbid")

  name: str
  column: str


class EntityBinding(BaseModel):
  """Realizes one ontology entity against a physical table or view.

  ``source`` is the physical table; to expose a filtered or joined slice
  (``type = 'customer'``, etc.) build a view in the warehouse and bind
  to that view rather than extending this model with expressions.

  The primary key is implicit: the ontology names the key properties,
  and the matching ``PropertyBinding`` entries here supply the columns.
  """

  model_config = ConfigDict(extra="forbid")

  name: str
  source: str
  # An empty list is accepted so this shape model stays ontology-free;
  # whether an empty list is *correct* depends on how many non-derived
  # properties the bound entity declares, which only the loader can
  # answer. A strict non-empty check here would false-positive on
  # entities that legitimately have no non-derived properties.
  properties: list[PropertyBinding] = Field(default_factory=list)


class RelationshipBinding(BaseModel):
  """Realizes one ontology relationship against a physical edge table.

  ``from_columns`` and ``to_columns`` are the columns in ``source`` that
  carry the source and target endpoint keys — a list because primary
  keys may be composite. Their arity must equal the corresponding
  endpoint entity's primary-key arity, which only the loader can check
  against the ontology; the ``min_length=1`` guard here just rejects
  the structurally-invalid empty list.
  """

  model_config = ConfigDict(extra="forbid")

  name: str
  source: str
  from_columns: list[str] = Field(min_length=1)
  to_columns: list[str] = Field(min_length=1)
  properties: list[PropertyBinding] = Field(default_factory=list)


class Binding(BaseModel):
  """Root of a binding YAML document.

  ``binding`` is this document's own name (typically suffixed with the
  environment, e.g. ``finance-bq-prod``). ``ontology`` is the *name* of
  the logical ontology this binding realizes — not a path; the loader
  resolves it to an ontology file.

  A binding may realize a *subset* of the referenced ontology: entities
  and relationships that are absent here are simply not realized on
  this target. Both ``entities`` and ``relationships`` default to empty
  so that parse-only shape checks succeed on minimal stub files; a
  binding that realizes nothing is semantically pointless but not
  shape-invalid.
  """

  model_config = ConfigDict(extra="forbid")

  binding: str
  ontology: str
  target: BigQueryTarget
  entities: list[EntityBinding] = Field(default_factory=list)
  relationships: list[RelationshipBinding] = Field(default_factory=list)
