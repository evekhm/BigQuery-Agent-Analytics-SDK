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

"""Live BigQuery integration tests for the ontology+binding runtime path.

These tests require:
  - RUN_LIVE_BIGQUERY_TESTS=1 (explicit opt-in)
  - GOOGLE_CLOUD_PROJECT env var set to a real GCP project
  - BigQuery API enabled with default credentials
  - The ``agent_events`` table with YMGO ADCP session data

Optional env vars:
  - BQ_LOCATION (default: US) — must match the source dataset's region
  - BQ_DATASET (default: agent_analytics)
  - BQ_TABLE (default: agent_events)
  - BQ_SESSION_ID (default: adcp-033c95d7a97d)

Run explicitly::

    RUN_LIVE_BIGQUERY_TESTS=1 GOOGLE_CLOUD_PROJECT=my-project \\
        pytest tests/test_integration_ontology_binding.py -v

Skipped automatically without the opt-in flag.
"""

from __future__ import annotations

import os
import uuid

import pytest

_LIVE = os.environ.get("RUN_LIVE_BIGQUERY_TESTS", "").lower() in (
    "1",
    "true",
    "yes",
)
_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
_DATASET = os.environ.get("BQ_DATASET", "agent_analytics")
_TABLE = os.environ.get("BQ_TABLE", "agent_events")
_SESSION = os.environ.get("BQ_SESSION_ID", "adcp-033c95d7a97d")
_LOCATION = os.environ.get("BQ_LOCATION", "US")

pytestmark = pytest.mark.skipif(
    not _LIVE or _PROJECT is None or _PROJECT == "your-project-id",
    reason=(
        "Live BQ tests require RUN_LIVE_BIGQUERY_TESTS=1 and "
        "GOOGLE_CLOUD_PROJECT set"
    ),
)


@pytest.fixture(scope="module")
def scratch_dataset():
  """Create a scratch dataset that auto-expires, yield it, then delete."""
  from google.cloud import bigquery

  run_id = uuid.uuid4().hex[:8]
  ds_id = f"{_DATASET}_integ_{run_id}"
  client = bigquery.Client(project=_PROJECT, location=_LOCATION)
  ds = bigquery.Dataset(f"{_PROJECT}.{ds_id}")
  ds.location = _LOCATION
  ds.default_table_expiration_ms = 3600000
  client.create_dataset(ds, exists_ok=True)
  yield ds_id
  client.delete_dataset(
      f"{_PROJECT}.{ds_id}", delete_contents=True, not_found_ok=True
  )


@pytest.fixture(scope="module")
def ontology_and_binding(scratch_dataset, tmp_path_factory):
  """Write ontology + binding YAML and load via upstream loaders."""
  from bigquery_ontology import load_binding
  from bigquery_ontology import load_ontology

  tmp = tmp_path_factory.mktemp("specs")

  ont_path = tmp / "ymgo.ontology.yaml"
  ont_path.write_text(
      "ontology: YMGO_Integration_Test\n"
      "entities:\n"
      "  - name: mako_DecisionPoint\n"
      "    keys:\n"
      "      primary: [decision_id]\n"
      "    properties:\n"
      "      - name: decision_id\n"
      "        type: string\n"
      "      - name: decision_type\n"
      "        type: string\n"
      "  - name: sup_YahooAdUnit\n"
      "    keys:\n"
      "      primary: [adUnitId]\n"
      "    properties:\n"
      "      - name: adUnitId\n"
      "        type: string\n"
      "      - name: adUnitName\n"
      "        type: string\n"
      "      - name: adUnitSize\n"
      "        type: string\n"
      "      - name: adUnitPosition\n"
      "        type: string\n"
      "relationships:\n"
      "  - name: CandidateEdge\n"
      "    from: mako_DecisionPoint\n"
      "    to: sup_YahooAdUnit\n"
      "    properties:\n"
      "      - name: edge_type\n"
      "        type: string\n"
      "      - name: mako_scoreValue\n"
      "        type: double\n"
      "  - name: sup_YahooAdUnitEvolvedFrom\n"
      "    from: sup_YahooAdUnit\n"
      "    to: sup_YahooAdUnit\n"
      "    properties:\n"
      "      - name: from_session_id\n"
      "        type: string\n"
      "      - name: to_session_id\n"
      "        type: string\n"
      "      - name: event_time\n"
      "        type: timestamp\n"
      "      - name: changed_properties\n"
      "        type: string\n",
      encoding="utf-8",
  )

  bnd_path = tmp / "ymgo-bq.binding.yaml"
  bnd_path.write_text(
      f"binding: ymgo_integ\n"
      f"ontology: YMGO_Integration_Test\n"
      f"target:\n"
      f"  backend: bigquery\n"
      f"  project: {_PROJECT}\n"
      f"  dataset: {scratch_dataset}\n"
      f"entities:\n"
      f"  - name: mako_DecisionPoint\n"
      f"    source: decision_points\n"
      f"    properties:\n"
      f"      - name: decision_id\n"
      f"        column: decision_id\n"
      f"      - name: decision_type\n"
      f"        column: decision_type\n"
      f"  - name: sup_YahooAdUnit\n"
      f"    source: yahoo_ad_units\n"
      f"    properties:\n"
      f"      - name: adUnitId\n"
      f"        column: adUnitId\n"
      f"      - name: adUnitName\n"
      f"        column: adUnitName\n"
      f"      - name: adUnitSize\n"
      f"        column: adUnitSize\n"
      f"      - name: adUnitPosition\n"
      f"        column: adUnitPosition\n"
      f"relationships:\n"
      f"  - name: CandidateEdge\n"
      f"    source: candidate_edges\n"
      f"    from_columns: [decision_id]\n"
      f"    to_columns: [adUnitId]\n"
      f"    properties:\n"
      f"      - name: edge_type\n"
      f"        column: edge_type\n"
      f"      - name: mako_scoreValue\n"
      f"        column: mako_scoreValue\n"
      f"  - name: sup_YahooAdUnitEvolvedFrom\n"
      f"    source: sup_yahoo_ad_unit_lineage\n"
      f"    from_columns: [adUnitId]\n"
      f"    to_columns: [adUnitId]\n"
      f"    properties:\n"
      f"      - name: from_session_id\n"
      f"        column: from_session_id\n"
      f"      - name: to_session_id\n"
      f"        column: to_session_id\n"
      f"      - name: event_time\n"
      f"        column: event_time\n"
      f"      - name: changed_properties\n"
      f"        column: changed_properties\n",
      encoding="utf-8",
  )

  ontology = load_ontology(str(ont_path))
  binding = load_binding(str(bnd_path), ontology=ontology)
  return ontology, binding


@pytest.fixture(scope="module")
def lineage_config():
  from bigquery_agent_analytics.runtime_spec import LineageEdgeConfig

  return {
      "sup_YahooAdUnitEvolvedFrom": LineageEdgeConfig(
          from_session_column="from_session_id",
          to_session_column="to_session_id",
      ),
  }


class TestExtraction:
  """Live extraction via from_ontology_binding."""

  def test_extract_returns_nodes(self, ontology_and_binding, lineage_config):
    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager

    ontology, binding = ontology_and_binding
    mgr = OntologyGraphManager.from_ontology_binding(
        project_id=_PROJECT,
        dataset_id=_DATASET,
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
        table_id=_TABLE,
    )
    graph = mgr.extract_graph(session_ids=[_SESSION], use_ai_generate=True)
    assert len(graph.nodes) > 0, "Expected at least 1 node from extraction"


class TestMaterialization:
  """Live materialization via from_ontology_binding."""

  def test_create_tables_and_materialize(
      self, ontology_and_binding, lineage_config, scratch_dataset
  ):
    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager
    from bigquery_agent_analytics.ontology_materializer import OntologyMaterializer

    ontology, binding = ontology_and_binding

    # Extract.
    mgr = OntologyGraphManager.from_ontology_binding(
        project_id=_PROJECT,
        dataset_id=_DATASET,
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
        table_id=_TABLE,
    )
    graph = mgr.extract_graph(session_ids=[_SESSION], use_ai_generate=True)
    assert len(graph.nodes) > 0

    # Materialize.
    mat = OntologyMaterializer.from_ontology_binding(
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
        write_mode="batch_load",
    )
    tables = mat.create_tables()
    assert len(tables) > 0, "Expected tables to be created"

    result = mat.materialize_with_status(graph, [_SESSION])
    assert (
        sum(result.row_counts.values()) > 0
    ), "Expected at least 1 row materialized"
    for ts in result.table_statuses.values():
      if ts.rows_inserted > 0:
        assert (
            ts.idempotent is True
        ), f"{ts.table_ref}: expected idempotent=True"


class TestPropertyGraph:
  """Live DDL + GQL via from_ontology_binding."""

  def test_create_graph_and_query(
      self, ontology_and_binding, lineage_config, scratch_dataset
  ):
    from google.cloud import bigquery

    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager
    from bigquery_agent_analytics.ontology_materializer import OntologyMaterializer
    from bigquery_agent_analytics.ontology_orchestrator import compile_showcase_gql
    from bigquery_agent_analytics.ontology_property_graph import OntologyPropertyGraphCompiler

    ontology, binding = ontology_and_binding

    # Extract + materialize.
    mgr = OntologyGraphManager.from_ontology_binding(
        project_id=_PROJECT,
        dataset_id=_DATASET,
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
        table_id=_TABLE,
    )
    graph = mgr.extract_graph(session_ids=[_SESSION], use_ai_generate=True)

    mat = OntologyMaterializer.from_ontology_binding(
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
        write_mode="batch_load",
    )
    mat.create_tables()
    mat.materialize_with_status(graph, [_SESSION])

    # Create property graph.
    compiler = OntologyPropertyGraphCompiler.from_ontology_binding(
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
    )
    created = compiler.create_property_graph()
    assert created is True, "Property Graph creation failed"

    # Run GQL query.
    gql = compile_showcase_gql(mgr.spec, _PROJECT, scratch_dataset)
    client = bigquery.Client(project=_PROJECT, location=_LOCATION)
    job = client.query(
        gql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("session_id", "STRING", _SESSION),
                bigquery.ScalarQueryParameter("result_limit", "INT64", 50),
            ]
        ),
    )
    rows = list(job.result())
    assert len(rows) > 0, "GQL query returned 0 rows"


class TestLineageEndToEnd:
  """Live lineage detection + GQL via from_ontology_binding."""

  def test_synthetic_lineage_query(
      self, ontology_and_binding, lineage_config, scratch_dataset
  ):
    from google.cloud import bigquery

    from bigquery_agent_analytics.ontology_graph import detect_lineage_edges
    from bigquery_agent_analytics.ontology_graph import OntologyGraphManager
    from bigquery_agent_analytics.ontology_materializer import OntologyMaterializer
    from bigquery_agent_analytics.ontology_models import ExtractedGraph
    from bigquery_agent_analytics.ontology_models import ExtractedNode
    from bigquery_agent_analytics.ontology_models import ExtractedProperty
    from bigquery_agent_analytics.ontology_orchestrator import compile_lineage_gql
    from bigquery_agent_analytics.ontology_property_graph import OntologyPropertyGraphCompiler

    ontology, binding = ontology_and_binding

    # Extract session A.
    mgr = OntologyGraphManager.from_ontology_binding(
        project_id=_PROJECT,
        dataset_id=_DATASET,
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
        table_id=_TABLE,
    )
    graph_a = mgr.extract_graph(session_ids=[_SESSION], use_ai_generate=True)
    assert len(graph_a.nodes) > 0

    # Build synthetic session B.
    ad_units = [n for n in graph_a.nodes if n.entity_name == "sup_YahooAdUnit"]
    assert len(ad_units) > 0, "No ad units extracted from session A"

    original = ad_units[0]
    orig_props = {p.name: p.value for p in original.properties}
    shared_id = orig_props.get("adUnitId", "unknown")

    synthetic = ExtractedNode(
        node_id=f"sess-integ-B:sup_YahooAdUnit:adUnitId={shared_id}",
        entity_name="sup_YahooAdUnit",
        labels=["sup_YahooAdUnit"],
        properties=[
            ExtractedProperty(name="adUnitId", value=shared_id),
            ExtractedProperty(
                name="adUnitName",
                value=orig_props.get("adUnitName", "") + " (Integ Test)",
            ),
            ExtractedProperty(
                name="adUnitSize",
                value=orig_props.get("adUnitSize", "300x250"),
            ),
            ExtractedProperty(name="adUnitPosition", value="BTF"),
        ],
    )
    graph_b = ExtractedGraph(name=mgr.spec.name, nodes=[synthetic], edges=[])

    # Detect lineage.
    lineage_edges = detect_lineage_edges(
        current_graph=graph_b,
        current_session_id="sess-integ-B",
        prior_graphs={_SESSION: graph_a},
        lineage_entity_types=["sup_YahooAdUnit"],
        spec=mgr.spec,
    )
    assert len(lineage_edges) > 0, "Expected at least 1 lineage edge"

    # Materialize all.
    mat = OntologyMaterializer.from_ontology_binding(
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
        write_mode="batch_load",
    )
    mat.create_tables()
    mat.materialize_with_status(graph_a, [_SESSION])
    mat.materialize_with_status(graph_b, ["sess-integ-B"])

    lineage_graph = ExtractedGraph(
        name=mgr.spec.name, nodes=[], edges=lineage_edges
    )
    mat.materialize_with_status(lineage_graph, ["sess-integ-B"])

    # Create property graph + run lineage GQL.
    compiler = OntologyPropertyGraphCompiler.from_ontology_binding(
        ontology=ontology,
        binding=binding,
        lineage_config=lineage_config,
    )
    created = compiler.create_property_graph()
    assert created is True

    lineage_gql = compile_lineage_gql(
        spec=mgr.spec,
        project_id=_PROJECT,
        dataset_id=scratch_dataset,
        relationship_name="sup_YahooAdUnitEvolvedFrom",
    )
    client = bigquery.Client(project=_PROJECT, location=_LOCATION)
    job = client.query(
        lineage_gql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "session_id", "STRING", "sess-integ-B"
                ),
                bigquery.ScalarQueryParameter("result_limit", "INT64", 50),
            ]
        ),
    )
    rows = list(job.result())
    assert len(rows) > 0, "Lineage GQL returned 0 rows"
