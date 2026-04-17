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

"""Tests for runtime class from_ontology_binding() factory methods."""

from __future__ import annotations

from unittest.mock import MagicMock

from bigquery_ontology import BigQueryTarget
from bigquery_ontology import Binding
from bigquery_ontology import Entity
from bigquery_ontology import EntityBinding
from bigquery_ontology import Keys
from bigquery_ontology import Ontology
from bigquery_ontology import Property
from bigquery_ontology import PropertyBinding
from bigquery_ontology import PropertyType
from bigquery_ontology import Relationship
from bigquery_ontology import RelationshipBinding


def _simple_ontology():
  return Ontology(
      ontology="shop",
      entities=[
          Entity(
              name="Customer",
              keys=Keys(primary=["cid"]),
              properties=[
                  Property(name="cid", type=PropertyType.STRING),
                  Property(name="name", type=PropertyType.STRING),
              ],
          ),
          Entity(
              name="Order",
              keys=Keys(primary=["oid"]),
              properties=[
                  Property(name="oid", type=PropertyType.STRING),
              ],
          ),
      ],
      relationships=[
          Relationship(
              name="Placed",
              **{"from": "Customer"},
              to="Order",
          ),
      ],
  )


def _simple_binding():
  return Binding(
      binding="shop_bq",
      ontology="shop",
      target=BigQueryTarget(
          backend="bigquery",
          project="proj",
          dataset="ds",
      ),
      entities=[
          EntityBinding(
              name="Customer",
              source="customers",
              properties=[
                  PropertyBinding(name="cid", column="cid"),
                  PropertyBinding(name="name", column="name"),
              ],
          ),
          EntityBinding(
              name="Order",
              source="orders",
              properties=[
                  PropertyBinding(name="oid", column="oid"),
              ],
          ),
      ],
      relationships=[
          RelationshipBinding(
              name="Placed",
              source="placed",
              from_columns=["cid"],
              to_columns=["oid"],
          ),
      ],
  )


class TestGraphManagerFactory:
  """OntologyGraphManager.from_ontology_binding()."""

  def test_creates_manager(self):
    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager

    mgr = OntologyGraphManager.from_ontology_binding(
        project_id="proj",
        dataset_id="ds",
        ontology=_simple_ontology(),
        binding=_simple_binding(),
    )
    assert isinstance(mgr, OntologyGraphManager)
    assert mgr.spec.name == "shop"
    assert len(mgr.spec.entities) == 2

  def test_extractors_passed_through(self):
    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager

    dummy_extractor = lambda event, spec: None
    mgr = OntologyGraphManager.from_ontology_binding(
        project_id="proj",
        dataset_id="ds",
        ontology=_simple_ontology(),
        binding=_simple_binding(),
        extractors={"TEST": dummy_extractor},
    )
    assert "TEST" in mgr.extractors

  def test_spec_is_valid(self):
    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager
    from bigquery_agent_analytics.resolved_spec import ResolvedGraph

    mgr = OntologyGraphManager.from_ontology_binding(
        project_id="proj",
        dataset_id="ds",
        ontology=_simple_ontology(),
        binding=_simple_binding(),
    )
    # Spec must be a valid ResolvedGraph with entities and relationships.
    assert isinstance(mgr.spec, ResolvedGraph)
    assert len(mgr.spec.entities) > 0
    assert len(mgr.spec.relationships) > 0


class TestMaterializerFactory:
  """OntologyMaterializer.from_ontology_binding()."""

  def test_creates_materializer(self):
    from bigquery_agent_analytics.ontology_materializer import OntologyMaterializer

    mat = OntologyMaterializer.from_ontology_binding(
        ontology=_simple_ontology(),
        binding=_simple_binding(),
    )
    assert isinstance(mat, OntologyMaterializer)
    assert mat.spec.name == "shop"

  def test_project_from_binding_target(self):
    from bigquery_agent_analytics.ontology_materializer import OntologyMaterializer

    mat = OntologyMaterializer.from_ontology_binding(
        ontology=_simple_ontology(),
        binding=_simple_binding(),
    )
    # project/dataset come from binding.target, not constructor args.
    assert mat.project_id == "proj"
    assert mat.dataset_id == "ds"

  def test_write_mode_passed_through(self):
    from bigquery_agent_analytics.ontology_materializer import OntologyMaterializer

    mat = OntologyMaterializer.from_ontology_binding(
        ontology=_simple_ontology(),
        binding=_simple_binding(),
        write_mode="batch_load",
    )
    assert mat.write_mode == "batch_load"


class TestCompilerFactory:
  """OntologyPropertyGraphCompiler.from_ontology_binding()."""

  def test_creates_compiler(self):
    from bigquery_agent_analytics.ontology_property_graph import OntologyPropertyGraphCompiler

    compiler = OntologyPropertyGraphCompiler.from_ontology_binding(
        ontology=_simple_ontology(),
        binding=_simple_binding(),
    )
    assert isinstance(compiler, OntologyPropertyGraphCompiler)
    assert compiler.spec.name == "shop"
    # project/dataset from binding.target.
    assert compiler.project_id == "proj"
    assert compiler.dataset_id == "ds"

  def test_ddl_generated(self):
    from bigquery_agent_analytics.ontology_property_graph import OntologyPropertyGraphCompiler

    compiler = OntologyPropertyGraphCompiler.from_ontology_binding(
        ontology=_simple_ontology(),
        binding=_simple_binding(),
    )
    ddl = compiler.get_ddl()
    assert "CREATE OR REPLACE PROPERTY GRAPH" in ddl
    assert "Customer" in ddl
    assert "Order" in ddl
    assert "Placed" in ddl


class TestEndToEnd:
  """Full pipeline via from_ontology_binding() entry points."""

  def test_extract_materialize_ddl(self):
    """All three runtime classes work from the same Ontology+Binding."""
    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager
    from bigquery_agent_analytics.ontology_materializer import OntologyMaterializer
    from bigquery_agent_analytics.ontology_property_graph import OntologyPropertyGraphCompiler

    ont = _simple_ontology()
    bnd = _simple_binding()

    # Graph manager takes explicit project/dataset for telemetry source.
    mgr = OntologyGraphManager.from_ontology_binding(
        project_id="proj",
        dataset_id="ds",
        ontology=ont,
        binding=bnd,
    )
    # Materializer and compiler derive project/dataset from binding.
    mat = OntologyMaterializer.from_ontology_binding(
        ontology=ont,
        binding=bnd,
        write_mode="batch_load",
    )
    compiler = OntologyPropertyGraphCompiler.from_ontology_binding(
        ontology=ont,
        binding=bnd,
    )

    # All three share the same spec shape.
    assert mgr.spec.name == mat.spec.name == compiler.spec.name
    assert (
        len(mgr.spec.entities)
        == len(mat.spec.entities)
        == len(compiler.spec.entities)
    )

    # DDL is generated.
    ddl = compiler.get_ddl()
    assert "CREATE OR REPLACE PROPERTY GRAPH" in ddl
