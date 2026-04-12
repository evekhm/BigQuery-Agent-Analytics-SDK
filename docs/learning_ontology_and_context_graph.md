# Ontology and Context Graph: A Comprehensive Learning Guide

This document synthesizes learnings from Microsoft's
[Ontology-Playground](https://github.com/microsoft/Ontology-Playground),
W3C standards (OWL, RDF), Azure Digital Twins (DTDL), and our own SDK's
context graph and ontology extraction pipeline. It is aimed at engineers
who want to understand how ontologies work, why they matter for AI agent
systems, and how the BigQuery Agent Analytics SDK applies these concepts.

---

## Table of Contents

1. [What Is an Ontology?](#1-what-is-an-ontology)
2. [The Three Graph Models](#2-the-three-graph-models)
3. [Ontology Standards Landscape](#3-ontology-standards-landscape)
4. [Design Patterns for Ontologies](#4-design-patterns-for-ontologies)
5. [Microsoft Ontology-Playground: Case Study](#5-microsoft-ontology-playground-case-study)
6. [Context Graphs for AI Agent Systems](#6-context-graphs-for-ai-agent-systems)
7. [How the BQAA SDK Implements These Concepts](#7-how-the-bqaa-sdk-implements-these-concepts)
8. [Comparing Approaches](#8-comparing-approaches)
9. [Recommended Reading](#9-recommended-reading)

---

## 1. What Is an Ontology?

An ontology is a **formal, explicit specification of a shared
conceptualization of a domain**. In practical terms, it defines:

- **Entity types** (classes) — the kinds of things that exist
  (Customer, Order, Product)
- **Properties** (attributes) — typed data each entity carries
  (name: string, amount: decimal)
- **Relationships** — how entity types connect to each other
  (Customer *places* Order, Order *contains* Product)
- **Constraints** — rules about cardinality, valid values, required
  fields, and type hierarchies

The key distinction from a database schema: an ontology captures
**meaning**, not just structure. It answers "what does this thing
represent in the real world?" rather than "what columns does this
table have?"

### Why Ontologies Matter for AI

Without an ontology, the word "diagnosis" could mean a medical finding
or a software analysis. With one, the type system disambiguates.
Research shows ontology-grounded knowledge graphs achieve **98%
accuracy vs. 37% for ungrounded LLMs**, reducing hallucination from
63% to 1.7% (PubMed 2025, clinical study).

Ontologies give AI agents:
- **Semantic grounding** — formal definitions constrain LLM output
- **Multi-hop reasoning** — traversal follows typed relationships,
  not just vector similarity
- **Auditability** — every extracted entity has a type, provenance,
  and position in the graph

---

## 2. The Three Graph Models

Three distinct but related concepts are often conflated. Understanding
their differences is essential.

### Property Graph

A graph where both **nodes and edges carry key-value properties**.
Nodes have labels (types); edges have types and direction.

```
(alice:Customer {name: "Alice", tier: "Gold"})
  -[:PLACES {date: "2026-01-15"}]->
(order1:Order {total: 99.50})
```

- **Standards**: No universal standard yet (Neo4j, TinkerPop, ISO GQL
  emerging)
- **Strengths**: Developer-friendly, performant traversal, rich edge
  properties
- **Used by**: Neo4j, BigQuery Property Graphs, Amazon Neptune,
  TigerGraph

### Knowledge Graph

A network of **real-world entities grounded in semantics**. Instance
data structured according to an ontology.

```
:alice  rdf:type  :Customer .
:alice  :places   :order1 .
:order1 :total    "99.50"^^xsd:decimal .
```

- **Standards**: RDF triples (subject-predicate-object), SPARQL for
  querying
- **Strengths**: Formal semantics, automated reasoning, cross-domain
  linkage
- **Used by**: Google Knowledge Graph, Wikidata, enterprise knowledge
  management

### Ontology

The **abstract schema** that defines what types of things exist and how
they relate. Not the data itself.

```
:Customer  rdf:type      owl:Class .
:places    rdf:type      owl:ObjectProperty ;
           rdfs:domain   :Customer ;
           rdfs:range    :Order .
```

### The Equation

```
ontology + instance data = knowledge graph
```

An ontology is the schema; a knowledge graph instantiates it with
concrete entities. A property graph is an implementation format for
either.

---

## 3. Ontology Standards Landscape

### OWL (Web Ontology Language)

The W3C standard for defining ontologies on the semantic web. Built on
RDF and RDFS, grounded in Description Logic.

| Construct | Purpose | Example |
|-----------|---------|---------|
| `owl:Class` | Entity type | `Customer`, `Order` |
| `owl:ObjectProperty` | Relationship | `places`, `contains` |
| `owl:DatatypeProperty` | Attribute | `hasName`, `totalAmount` |
| `rdfs:subClassOf` | Inheritance | `PremiumCustomer` ⊂ `Customer` |
| Cardinality restrictions | Constraints | "exactly one identifier" |
| `owl:equivalentClass` | Equivalence | Two classes represent the same concept |
| `owl:disjointWith` | Exclusion | `Customer` and `Product` cannot overlap |

**Key characteristic**: Open World Assumption — what is not stated is
not assumed false. This is the opposite of databases (Closed World
Assumption).

OWL has three expressiveness profiles:
- **OWL Lite** — classification hierarchies, simple constraints
- **OWL DL** — full Description Logic, decidable reasoning
- **OWL Full** — maximum expressiveness, undecidable

### RDF (Resource Description Framework)

The data model underlying OWL. Everything is a **triple**:
`(subject, predicate, object)`. Serialized as RDF/XML, Turtle, JSON-LD,
or N-Triples.

### DTDL (Digital Twin Definition Language)

Microsoft's JSON-LD-based modeling language for Azure Digital Twins.
Designed for IoT and building management.

| Construct | Purpose |
|-----------|---------|
| **Interface** | Top-level model unit (like a class) |
| **Property** | Stateful attribute with schema type |
| **Telemetry** | Time-series data (no backing storage) |
| **Relationship** | Typed edge to another Interface |
| **Component** | Embedded sub-interface (composition) |
| **Command** | Invocable operation |

**Identification**: Digital Twin Model Identifiers (DTMIs) —
`dtmi:com:example:Room;1` — globally unique and versioned.

**Composition**:
- `extends` for inheritance (up to 10 levels deep)
- Components for embedding sub-interfaces
- Feature extensions (v3) for semantic types and units

### SHACL (Shapes Constraint Language)

W3C standard for validating RDF graphs against a set of constraints
("shapes"). Used alongside OWL when you need closed-world validation
on an open-world model.

### How They Compare

| Dimension | OWL/RDF | DTDL | YAML (BQAA SDK) |
|-----------|---------|------|------------------|
| Data model | Triple graph | Property graph (JSON-LD) | Property graph |
| Expressiveness | Full DL axioms | Practical/constrained | Minimal/focused |
| Reasoning | Automated (DL solvers) | None | None |
| World assumption | Open | Effectively closed | Closed |
| IoT integration | Requires SSN/SOSA | Native | N/A (agent traces) |
| Developer accessibility | Steep | Moderate (JSON) | Low (YAML) |
| Physical bindings | No | No | Yes (BQ tables) |

---

## 4. Design Patterns for Ontologies

### Naming Conventions

These patterns are consistent across Microsoft's Ontology-Playground,
Azure Digital Twins, and our own SDK:

| Element | Convention | Good | Bad |
|---------|-----------|------|-----|
| Entity types | Singular, TitleCase | `Customer` | `tbl_cust`, `Customers` |
| Properties | camelCase, descriptive | `loyaltyTier` | `lt`, `TIER_LVL` |
| Relationships | Verb-based, short | `places`, `contains` | `ownership`, `linked_to` |
| IDs | Lowercase slugs | `customer`, `work-order` | `CUST_01` |

### Structural Patterns

**One entity, one concept**: Avoid "god entities" with 30+ unrelated
properties. If an entity models multiple real-world things, split it.

**Sweet spot sizing**: 3-8 entity types per ontology, 1-2
relationships per entity. Larger ontologies should be composed from
smaller modules.

**Identifier discipline**: Every entity type must have at least one
primary key column. The SDK's `KeySpec.primary` accepts a list, so
composite primary keys are supported (e.g., `[region, customer_id]`).
This is similarly enforced in the Ontology-Playground and Azure Digital
Twins, though those ecosystems typically use a single `@id` field.

**Extension over modification**: Never modify a base ontology directly.
Add new interfaces that `extend` existing ones. This pattern is
critical for Azure Digital Twins industry ontologies (RealEstateCore)
and maps to OWL's `rdfs:subClassOf`.

### Composition Patterns

| Pattern | Description | Example |
|---------|-------------|---------|
| **Inheritance** | Child type inherits parent's meaning/labels | `PremiumCustomer extends Customer` |
| **Composition** | Embed sub-models as named components | DTDL Components |
| **Modular decomposition** | Independent ontology modules with defined dependencies | FIBO subsets |
| **Progressive building** | Start small (3 entities), add 2-3 per iteration | Ontology-Playground lab steps |

### Anti-Patterns

- **God entity**: One class with 30+ properties modeling multiple concepts
- **Generic names**: `Item`, `Thing`, `Record`, `Data`
- **Noun-based relationships**: `ownership` instead of `owns`
- **Missing identifiers**: Entities without primary keys
- **Over-modeling**: Not every internal table needs an ontology entity
- **Circular one-to-ones**: Probably the same entity — merge them

---

## 5. Microsoft Ontology-Playground: Case Study

The [Ontology-Playground](https://github.com/microsoft/Ontology-Playground)
is an open-source web application for learning ontology concepts and
authoring ontologies for Microsoft Fabric IQ.

### Architecture

The current repository is best understood as a **static ontology
platform**, not just a diagram editor. It is a React + TypeScript + Vite
application with zero backend by default and a build-time compilation
pipeline:

1. **`catalogue/`** stores curated ontology examples and metadata, which
   are compiled into a searchable catalogue with deep links
2. **`content/learn/`** stores markdown learning content and quizzes,
   which are compiled into the "Ontology School" experience
3. **`scripts/`** handles catalogue compilation, learning-content
   compilation, and RDF round-trip validation
4. **`src/`** implements the graph explorer, visual designer, command
   palette, routing, and embeddable viewer
5. **`public/`** hosts static assets for GitHub Pages / static-site
   deployment
6. **`api/`** is optional and supports advanced flows like AI-assisted
   ontology building or GitHub contribution helpers when enabled

This separation is a useful design pattern: ontology content, pedagogy,
and visualization are versioned as source artifacts, then compiled into
static JSON/HTML assets for distribution.

### Product Surface

The current repo exposes several distinct product surfaces:

- **Interactive Graph Exploration** — Cytoscape.js-based ontology
  visualization with search, click-to-inspect, and shareable routes
- **Visual Ontology Designer** — split-pane editor with undo/redo,
  validation, RDF/XML export, and JSON export
- **Ontology School** — structured courses, progressive domain learning
  paths, quizzes, and presentation-mode articles
- **Embeddable Widget** — a standalone viewer that can be injected into
  other web pages
- **Catalogue Contribution Flow** — GitHub sign-in and one-click PR
  creation for submitting ontology entries
- **Natural Language Query Playground** — early NL-to-ontology mapping
  interface for Fabric IQ-style interaction

For our learning document, this matters because the Playground is not
just teaching OWL syntax. It is demonstrating how to **package ontology
knowledge as a developer product**: examples, tutorials, embedded
viewers, contribution workflows, and validation tooling all in one repo.

### Data Model

```typescript
interface Ontology {
  entityTypes: EntityType[];   // OWL Classes
  relationships: Relationship[]; // OWL ObjectProperties
}

interface EntityType {
  id: string;
  name: string;
  properties: Property[];     // OWL DatatypeProperties
  // icon (emoji), color (hex) for visualization
}

interface Relationship {
  from: string;  // source entity ID
  to: string;    // target entity ID
  cardinality: "one-to-one" | "one-to-many" | "many-to-one" | "many-to-many";
  attributes?: Property[];  // properties on the edge itself
}
```

### Serialization: RDF/XML with OWL

The canonical format is RDF/XML. The Playground maps its model to OWL:

| App Concept | OWL Mapping |
|-------------|-------------|
| EntityType | `owl:Class` |
| Property | `owl:DatatypeProperty` (with `rdfs:domain`, `rdfs:range` to XSD types) |
| Relationship | `owl:ObjectProperty` |
| Ontology metadata | `owl:Ontology` with `rdfs:label`, `rdfs:comment` |
| Custom annotations | `ont:` namespace (`ont:icon`, `ont:color`, `ont:cardinality`, etc.) |

The `ont:` custom namespace extends OWL without breaking compatibility.
This is a clean pattern for adding application-specific metadata to
standard ontology formats.

### Key Insights from the Playground

1. **Ontology as product, not just schema**: The repo combines
   catalogue, designer, learning paths, embeds, and contribution flow.
   That is a useful lesson for enterprise ontology work: adoption
   depends on tooling and pedagogy, not just expressiveness.

2. **Relationship attributes**: Modeled as `owl:DatatypeProperty` with
   an `ont:relationshipAttributeOf` annotation linking them to the
   `owl:ObjectProperty`. This is a pragmatic solution since OWL
   cannot natively attach properties to object properties.

3. **Round-trip validation**: The build pipeline serializes then
   re-parses every RDF file to verify fidelity. This catches subtle
   serialization bugs early.

4. **Static-first distribution**: The repo is designed to run as a
   static site with zero backend by default. This keeps ontology
   learning and visualization easy to deploy, fork, and review.

5. **Progressive disclosure**: Learning paths start with 3 entities
   and add 2-3 per step, with diff highlighting showing what changed.
   This mirrors our V4 ontology design philosophy.

6. **Embeddability matters**: The standalone viewer makes ontologies
   portable across docs, courseware, and apps. This is directly relevant
   to our own demos and educational materials.

### Domain Coverage

| Domain | Example | Entities |
|--------|---------|----------|
| Retail | Cosmic Coffee | Customer, Store, Product, Order, Region, Supplier |
| E-Commerce | Online commerce flow | Customer, Cart, Order, Product, Shipment |
| Healthcare | Clinical System | Patient, Provider, Encounter, Diagnosis, Medication |
| Finance | Banking | Account, Customer, Transaction, Branch, LoanProduct |
| Manufacturing | Industry 4.0 | WorkOrder, Machine, ProductionLine, Part, QualityCheck |
| Education | University | Student, Course, Instructor, Department, Enrollment |

External adapted ontologies: **FIBO** (financial industry), **Schema.org**
(events, businesses, creative works), **Pizza Ontology** (classic OWL
teaching example).

The "Ontology School" surface in the repo turns these examples into
guided learning assets: core ontology fundamentals, six domain-specific
learning paths, and a hands-on lab that progressively grows a supply
chain ontology from a small seed graph to a richer domain model.

---

## 6. Context Graphs for AI Agent Systems

A **context graph** is a knowledge graph purpose-built for AI
consumption. It extends a traditional knowledge graph with three
additional layers:

### Layer 1: Ontological Grounding

Formal semantic contracts (via OWL classes, YAML specs, or DTDL
interfaces) that make facts unambiguous. The ontology constrains what
the LLM can extract and how it interprets relationships.

### Layer 2: AI-Optimized Retrieval

Subgraph extraction formatted for LLM context windows. Instead of
dumping raw triples, the retrieval layer uses the ontology to:
- Follow typed relationships (semantic path traversal)
- Filter by entity type relevance
- Format as structured text (JSON-LD, Markdown tables, Turtle)

This is "Ontology RAG" — using the schema to guide retrieval rather
than relying solely on vector similarity.

### Layer 3: Reification of Agent Behavior

Agent actions, tool calls, decisions, and timestamps are encoded
directly into the graph as first-class nodes. This makes agent
interactions:
- **Auditable** — every decision has a typed node with provenance
- **Temporally traceable** — timestamps on nodes and edges
- **Learnable** — patterns in the graph reveal agent behavior

### Why This Matters: The Evidence

| Metric | Without Ontology | With Ontology |
|--------|-----------------|---------------|
| Factual accuracy | 37% | 98% |
| Hallucination rate | 63% | 1.7% |
| Multi-hop reasoning | Vector similarity only | Typed path traversal |
| Governance | Manual re-mapping | Formal definitions |

Source: PubMed 2025 clinical study on ontology-grounded KGs.

### Three-Layer Ontological Framework for Enterprise Agents

Recent research (arXiv, April 2025) proposes a neurosymbolic
architecture:

- **Role Ontology** — what the agent is and can do
- **Domain Ontology** — entities, relationships, and constraints in the
  business domain
- **Interaction Ontology** — conversational patterns and workflow logic

Our SDK's context graph maps to this framework: the `agent_events`
schema defines the Role Ontology (event types, agent capabilities),
the YAML-driven extraction defines the Domain Ontology, and the
decision semantics (V3) capture the Interaction Ontology.

---

## 7. How the BQAA SDK Implements These Concepts

The SDK has evolved through three generations, each adding ontological
sophistication.

### V2: Hard-Coded 4-Pillar Context Graph

The original design with two node types and two edge types:

```
TechNode (agent_events) --[Caused]--> TechNode
TechNode --[Evaluated]--> BizNode (extracted business entities)
```

- **TechNode**: Spans from the `agent_events` table (LLM calls, tool
  invocations, agent completions). Keyed by `span_id`.
- **BizNode**: Business entities extracted by `AI.GENERATE` per-span.
  Keyed by `span_id:node_type:node_value`.
- **Caused**: Parent-child span lineage from OpenTelemetry tracing.
- **Evaluated**: Cross-link from technical execution to business domain.

Entity types were hard-coded (Product, Campaign, Budget, etc.).

### V3: 6-Pillar with Decision Semantics

Added two new node types for EU audit compliance:

```
TechNode --[MadeDecision]--> DecisionPoint
DecisionPoint --[CandidateEdge]--> CandidateNode
```

- **DecisionPoint**: Captures where the agent chose between options.
- **CandidateNode**: Each option considered, with score, status
  (SELECTED/DROPPED), and rejection rationale.
- **World-change detection**: Fail-closed safety check for entity
  drift in long-running A2A tasks.

### V4: YAML-Driven Ontology Extraction

The current generation generalizes everything into a
**configuration-driven pipeline**:

```
YAML spec
  → Schema Compiler (output_schema + extraction prompt)
    → AI.GENERATE (per-session extraction)
      → Hydration (JSON → typed nodes + edges)
        → Materialization (BigQuery tables)
          → Property Graph DDL (CREATE PROPERTY GRAPH)
            → GQL queries (MATCH patterns)
```

#### The YAML Spec

A single YAML file defines the entire ontology. The top-level `graph:`
wrapper is required by `load_graph_spec()`:

```yaml
graph:
  name: ad_campaign_ontology
  entities:
    - name: Campaign
      description: An advertising campaign
      extends: MarketingAsset    # label inheritance
      binding:
        source: campaigns        # BigQuery table
      keys:
        primary: [campaign_id]   # list — composite keys supported
      properties:
        - name: campaign_id
          type: string
        - name: budget
          type: double
        - name: status
          type: string

  relationships:
    - name: targets
      from_entity: Campaign
      to_entity: Audience
      binding:
        source: campaign_audiences
        from_columns: [campaign_id]
        to_columns: [audience_id]
      properties:
        - name: bid_amount
          type: double
```

#### Key Design Decisions

**Configuration-over-code**: The YAML spec is the single source of
truth. The same file drives prompt generation, output schema
compilation, table DDL, property graph DDL, and GQL generation. No
code changes needed to model a new domain.

**Two-layer model separation**: Spec models (schema-time Pydantic) are
cleanly separated from extracted models (runtime Pydantic). This
prevents tight coupling between the ontology definition and the AI
extraction output.

**Label-only inheritance**: `extends` adds a parent label to a node
(like `rdfs:subClassOf`), but does NOT copy properties or bindings.
This maps directly to BigQuery Property Graph's multi-label support.

**Union flattening**: Since BigQuery's `AI.GENERATE` output schema
does not support `anyOf` / discriminated unions, all entity properties
are flattened into a single schema with an `entity_name` discriminator.
Type collisions across entities are detected at compile time.

**Deterministic key-based IDs**: Node IDs follow the pattern
`{session_id}:{entity_name}:{k1=v1,k2=v2}`. Edge references use the
same scheme via `from_keys`/`to_keys`. This makes deduplication
natural (last-write-wins for same key).

**Session-scoped idempotency**: Delete-then-insert ensures re-running
extraction for the same sessions produces identical results.

#### GQL Traversal

All graph queries use BigQuery's native GQL on Property Graphs:

```sql
-- V2/V3: quantified-path traversal (1-to-N causal hops + business cross-link)
GRAPH agent_context_graph
MATCH (decision:TechNode)-[c:Caused]->{1,20}(step:TechNode)
      -[e:Evaluated]->(biz:BizNode)
WHERE decision.session_id = @session_id

-- V4: spec-driven showcase query
GRAPH ontology_graph
MATCH (c:Campaign)-[t:targets]->(a:Audience)
WHERE c.session_id = @session_id
```

---

## 8. Comparing Approaches

| Dimension | Ontology-Playground | Azure Digital Twins | BQAA SDK V4 |
|-----------|--------------------|--------------------|-------------|
| **Schema language** | OWL (RDF/XML) | DTDL (JSON-LD) | YAML (custom) |
| **Entity modeling** | `owl:Class` | DTDL Interface | `EntitySpec` |
| **Properties** | `owl:DatatypeProperty` | DTDL Property/Telemetry | `PropertySpec` |
| **Relationships** | `owl:ObjectProperty` | DTDL Relationship | `RelationshipSpec` |
| **Inheritance** | Not supported | `extends` (multi-parent) | `extends` (label-only) |
| **Physical binding** | None | None (twin instance) | BQ table binding |
| **Extraction** | Manual authoring / AI builder | Manual upload | `AI.GENERATE` per-session |
| **Materialization** | Fabric IQ API | Azure Digital Twins API | BQ insert_rows_json |
| **Query language** | N/A (visualization only) | Azure DT Query Language | BigQuery GQL |
| **Target audience** | Business analysts | IoT / building engineers | ML / platform engineers |
| **AI integration** | Optional (GPT-4o-mini builder) | Event routing to downstream | Core (AI.GENERATE extraction) |

### Convergence Insight

The most significant finding across all three systems: **the same
ontological infrastructure that powers digital twin platforms is
precisely what AI agent systems need for semantic grounding**. Digital
twins model physical environments with formal schemas; context graphs
extend this by making the knowledge AI-consumable and by capturing
agent behavior as graph metadata.

The key difference is **direction of data flow**:
- Digital twins: sensors → ontology → digital twin graph → analytics
- Context graphs: agent traces → ontology → context graph → AI grounding

The ontology serves the same role in both: a formal contract that
constrains interpretation and enables structured traversal.

---

## 9. Recommended Reading

### Standards
- [OWL 2 Web Ontology Language Primer](https://www.w3.org/TR/owl2-primer/)
- [DTDL v3 Language Description](https://azure.github.io/opendigitaltwins-dtdl/DTDL/v3/DTDL.v3.html)
- [RDF 1.1 Primer](https://www.w3.org/TR/rdf11-primer/)
- [SHACL Specification](https://www.w3.org/TR/shacl/)

### Platforms
- [Azure Digital Twins — What Is an Ontology?](https://learn.microsoft.com/en-us/azure/digital-twins/concepts-ontologies)
- [Azure Digital Twins — Extending Ontologies](https://learn.microsoft.com/en-us/azure/digital-twins/concepts-ontologies-extend)
- [Microsoft Ontology-Playground (live)](https://microsoft.github.io/Ontology-Playground/)

### Industry Ontologies
- [RealEstateCore (smart buildings)](https://dev.realestatecore.io/docs/)
- [FIBO (financial industry)](https://spec.edmcouncil.org/fibo/)
- [Schema.org](https://schema.org/)

### AI + Ontologies
- [Ontology-grounded KGs for mitigating hallucinations (PubMed 2025)](https://pubmed.ncbi.nlm.nih.gov/41610815/)
- [Context Graph vs Knowledge Graph (TrustGraph)](https://trustgraph.ai/guides/key-concepts/context-graph-vs-knowledge-graph/)
- [Ontology-Constrained Neural Reasoning in Enterprise Agentic Systems (arXiv 2025)](https://arxiv.org/html/2604.00555)

### This SDK
- [Context Graph V2 Design](context_graph_v2_design.md)
- [Context Graph V3 Design](context_graph_v3_design.md)
- [Ontology Graph V4 Design](ontology_graph_v4_design.md)
