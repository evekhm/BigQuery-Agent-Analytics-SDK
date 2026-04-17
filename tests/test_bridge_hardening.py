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

"""Bridge hardening tests (Phase 2.75).

The same logical spec is loaded via the separated Ontology+Binding path
and the legacy combined GraphSpec path, then fed to every downstream
consumer. The tests prove:

  - **Byte-identical output** for in-SDK consumers: extraction prompt,
    output schema, showcase GQL, property-graph DDL (SDK compiler),
    and materialization schema columns.
  - **Valid output with expected semantic enrichment** for the upstream
    DDL bridge (``compile_ddl_via_upstream``): the separated path
    emits ``column AS logical_name`` renames because ``ResolvedProperty``
    preserves both names, while the combined path emits bare column
    names because ``GraphSpec`` already discarded logical names.

Scope: bridge-compatible flat specs only. Specs using ``extends`` or
lineage session columns are excluded — those paths remain on the
legacy code until the ``extends`` ADR is resolved.
"""

from __future__ import annotations

from pathlib import Path
import textwrap

import pytest

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ONTOLOGY_PATH = str(_FIXTURES / "test_ontology.yaml")
_BINDING_PATH = str(_FIXTURES / "test_binding.yaml")
_COMBINED_SPEC_PATH = str(_FIXTURES / "test_combined_spec.yaml")


def _load_separated():
  """Load via the new separated Ontology+Binding path."""
  from bigquery_agent_analytics.resolved_spec import resolve
  from bigquery_ontology import load_binding
  from bigquery_ontology import load_ontology

  ontology = load_ontology(_ONTOLOGY_PATH)
  binding = load_binding(_BINDING_PATH, ontology=ontology)
  return resolve(ontology, binding)


def _load_combined():
  """Load via the public combined-spec entry point (load_resolved_graph)."""
  from bigquery_agent_analytics.resolved_spec import load_resolved_graph

  return load_resolved_graph(_COMBINED_SPEC_PATH)


class TestResolvedGraphEquivalence:
  """The core bridge test: both paths produce the same ResolvedGraph."""

  def test_graph_name_matches(self):
    sep = _load_separated()
    com = _load_combined()
    assert sep.name == com.name

  def test_entity_count_matches(self):
    sep = _load_separated()
    com = _load_combined()
    assert len(sep.entities) == len(com.entities)

  def test_entity_sources_match(self):
    sep = _load_separated()
    com = _load_combined()
    sep_src = {e.name: e.source for e in sep.entities}
    com_src = {e.name: e.source for e in com.entities}
    assert sep_src == com_src

  def test_entity_key_columns_match(self):
    sep = _load_separated()
    com = _load_combined()
    sep_keys = {e.name: e.key_columns for e in sep.entities}
    com_keys = {e.name: e.key_columns for e in com.entities}
    assert sep_keys == com_keys

  def test_entity_property_columns_match(self):
    sep = _load_separated()
    com = _load_combined()
    for se, ce in zip(
        sorted(sep.entities, key=lambda e: e.name),
        sorted(com.entities, key=lambda e: e.name),
    ):
      sep_cols = [p.column for p in se.properties]
      com_cols = [p.column for p in ce.properties]
      assert sep_cols == com_cols, f"Mismatch on {se.name}"

  def test_entity_labels_match(self):
    sep = _load_separated()
    com = _load_combined()
    sep_labels = {e.name: e.labels for e in sep.entities}
    com_labels = {e.name: e.labels for e in com.entities}
    assert sep_labels == com_labels

  def test_relationship_sources_match(self):
    sep = _load_separated()
    com = _load_combined()
    sep_src = {r.name: r.source for r in sep.relationships}
    com_src = {r.name: r.source for r in com.relationships}
    assert sep_src == com_src

  def test_relationship_endpoint_columns_match(self):
    sep = _load_separated()
    com = _load_combined()
    for sr, cr in zip(sep.relationships, com.relationships):
      assert sr.from_columns == cr.from_columns, f"from mismatch on {sr.name}"
      assert sr.to_columns == cr.to_columns, f"to mismatch on {sr.name}"

  def test_relationship_property_columns_match(self):
    sep = _load_separated()
    com = _load_combined()
    for sr, cr in zip(sep.relationships, com.relationships):
      sep_cols = [p.column for p in sr.properties]
      com_cols = [p.column for p in cr.properties]
      assert sep_cols == com_cols, f"Mismatch on {sr.name}"


class TestDownstreamConsumerEquivalence:
  """Both paths produce identical output from every downstream consumer."""

  def test_extraction_prompt_matches(self):
    from bigquery_agent_analytics.ontology_schema_compiler import compile_extraction_prompt

    sep = _load_separated()
    com = _load_combined()
    assert compile_extraction_prompt(sep) == compile_extraction_prompt(com)

  def test_output_schema_matches(self):
    from bigquery_agent_analytics.ontology_schema_compiler import compile_output_schema

    sep = _load_separated()
    com = _load_combined()
    assert compile_output_schema(sep) == compile_output_schema(com)

  def test_showcase_gql_matches(self):
    from bigquery_agent_analytics.ontology_orchestrator import compile_showcase_gql

    sep = _load_separated()
    com = _load_combined()
    sep_gql = compile_showcase_gql(sep, project_id="p", dataset_id="d")
    com_gql = compile_showcase_gql(com, project_id="p", dataset_id="d")
    assert sep_gql == com_gql

  def test_property_graph_ddl_matches(self):
    from bigquery_agent_analytics.ontology_property_graph import compile_property_graph_ddl

    sep = _load_separated()
    com = _load_combined()
    sep_ddl = compile_property_graph_ddl(sep, "p", "d")
    com_ddl = compile_property_graph_ddl(com, "p", "d")
    assert sep_ddl == com_ddl

  def test_materialization_schema_matches(self):
    """Both paths produce the same table DDL columns."""
    from bigquery_agent_analytics.ontology_materializer import _entity_columns
    from bigquery_agent_analytics.ontology_materializer import _relationship_columns

    sep = _load_separated()
    com = _load_combined()

    for se, ce in zip(
        sorted(sep.entities, key=lambda e: e.name),
        sorted(com.entities, key=lambda e: e.name),
    ):
      assert _entity_columns(se) == _entity_columns(ce), se.name

    for sr, cr in zip(sep.relationships, com.relationships):
      assert _relationship_columns(sr, sep) == _relationship_columns(
          cr, com
      ), sr.name


class TestUpstreamDDLBridge:
  """The upstream DDL bridge (compile_ddl_via_upstream) coverage.

  The separated path produces richer DDL than the combined path because
  ResolvedProperty carries both ``column`` (physical) and ``logical_name``
  (ontology). The upstream compiler emits ``column AS logical_name`` for
  renames, while the combined path (where logical names are lost) emits
  bare column names. This is an expected and CORRECT difference — the
  separated path produces the semantically richer output.
  """

  def test_separated_ddl_has_column_renames(self):
    """Separated path emits 'cust_id AS customer_id' for renamed columns."""
    from bigquery_agent_analytics.ontology_property_graph import compile_ddl_via_upstream

    sep = _load_separated()
    ddl = compile_ddl_via_upstream(sep, "p", "d")
    # Physical column AS logical ontology name.
    assert "cust_id AS customer_id" in ddl
    assert "name AS display_name" in ddl

  def test_combined_ddl_has_bare_names(self):
    """Combined path emits bare 'cust_id' because logical names are lost."""
    from bigquery_agent_analytics.ontology_property_graph import compile_ddl_via_upstream

    com = _load_combined()
    ddl = compile_ddl_via_upstream(com, "p", "d")
    # No AS rename — combined GraphSpec already resolved to physical names.
    assert "cust_id AS customer_id" not in ddl
    # But the column is still present.
    assert "cust_id" in ddl

  def test_both_paths_produce_valid_ddl(self):
    """Both paths produce syntactically valid CREATE PROPERTY GRAPH."""
    from bigquery_agent_analytics.ontology_property_graph import compile_ddl_via_upstream

    sep = _load_separated()
    com = _load_combined()
    sep_ddl = compile_ddl_via_upstream(sep, "p", "d")
    com_ddl = compile_ddl_via_upstream(com, "p", "d")
    for ddl in (sep_ddl, com_ddl):
      assert ddl.startswith("CREATE PROPERTY GRAPH")
      assert "NODE TABLES" in ddl
      assert "EDGE TABLES" in ddl
