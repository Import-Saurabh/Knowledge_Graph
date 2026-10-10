# Graph Report - graph-app  (2026-10-12)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 319 nodes · 757 edges · 16 communities (9 shown, 7 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 83 edges (avg confidence: 0.92)
- Token cost: 812 input · 143 output

## Graph Freshness
- Built from commit: `d0d1bbd0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Graph Store API
- Article Ingestion Pipeline
- Graph Query Engine
- FastAPI App Setup
- DriftForge Assets & Diagrams
- CloudFront Log Shipper
- SQLite Database Layer
- Test Config & Fixtures
- Data Models & Schemas
- Entity Resolver & URL Normalization

## God Nodes (most connected - your core abstractions)
1. `GraphStore` - 58 edges
2. `get_db()` - 33 edges
3. `Article` - 20 edges
4. `GraphWriter` - 17 edges
5. `utc_now_iso()` - 15 edges
6. `IngestionPipeline` - 13 edges
7. `RSSConnector` - 13 edges
8. `QueryResearcher` - 13 edges
9. `QueryEngine` - 12 edges
10. `Entity` - 11 edges

## Surprising Connections (you probably didn't know these)
- `GitHub Actions Deploy Workflow` --references--> `Author Photo`  [EXTRACTED]
  .github/workflows/deploy.yml → photo.jpg
- `Author Photo` --references--> `3D News Knowledge Graph HTML`  [AMBIGUOUS]
  photo.jpg → index.html
- `test_conversations_and_messages()` --uses--> `GraphStore`  [INFERRED]
  tests/test_database.py → server/database.py
- `GitHub Actions Deploy Workflow` --references--> `DriftForge Favicon`  [EXTRACTED]
  .github/workflows/deploy.yml → favicon.svg
- `GitHub Actions Deploy Workflow` --references--> `Apple Touch Icon`  [EXTRACTED]
  .github/workflows/deploy.yml → apple-touch-icon.png

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **AWS Deployment Pipeline (Static Hosting + CI)** — github_workflows_deploy_yml, docker_compose_yml, architecture_md, requirements_txt [EXTRACTED 0.90]
- **Persistent Knowledge Stack (Schema + Phases 3–7 + README)** — sql_schema, implementation_plan_phase3, implementation_plan_phase4, implementation_plan_phase5, implementation_plan_phase6, implementation_plan_phase7, readme_md [EXTRACTED 0.95]
- **Cross-Page Navigation Surfaces (Graph ↔ Chat)** — index_html, chat_html, highlight_deep_link_flow, graph_chat_flow [EXTRACTED 0.95]

## Communities (16 total, 7 thin omitted)

### Community 0 - "Graph Store API"
Cohesion: 0.08
Nodes (15): GraphStore, Entity, Event, GraphResponse, Relationship, get_entity_detail(), get_event_detail(), get_graph() (+7 more)

### Community 1 - "Article Ingestion Pipeline"
Cohesion: 0.09
Nodes (9): LLMExtractor, IngestionPipeline, compute_sha256(), RSSConnector, GraphWriter, Article, IngestionJob, utc_now_iso() (+1 more)

### Community 2 - "Graph Query Engine"
Cohesion: 0.09
Nodes (10): QueryRequest, QueryResponse, QueryEngine, GraphRetriever, AnswerSynthesizer, create_conversation(), CreateConversationRequest, execute_query() (+2 more)

### Community 3 - "FastAPI App Setup"
Cohesion: 0.09
Nodes (9): health_check(), lifespan(), serve_chat(), serve_graph_json(), serve_root(), serve_version_json(), run_scheduled_ingestion(), shutdown_scheduler() (+1 more)

### Community 4 - "DriftForge Assets & Diagrams"
Cohesion: 0.10
Nodes (28): Apple Touch Icon, DriftForge AWS Architecture Diagram, Graph Chat Workspace HTML, Claude Command: Engagement Analytics, Claude Command: Visitor Trend, Claude Command: Visitor Summary, DriftForge Docker Compose, DriftForge Favicon (+20 more)

### Community 5 - "CloudFront Log Shipper"
Cohesion: 0.16
Nodes (15): alert_new_ip(), edge_to_city(), ensure_log_group(), is_bot(), lambda_handler(), load_known_ips(), parse_line(), save_known_ips() (+7 more)

### Community 6 - "SQLite Database Layer"
Cohesion: 0.13
Nodes (6): get_db(), get_db_connection(), init_db(), seed_from_graph_json_if_empty(), Message, test_conversations_and_messages()

### Community 8 - "Data Models & Schemas"
Cohesion: 0.15
Nodes (10): Citation, Claim, Conversation, EntityType, GraphLink, GraphNode, HealthResponse, IngestRequest (+2 more)

### Community 9 - "Entity Resolver & URL Normalization"
Cohesion: 0.17
Nodes (8): EntityResolver, slugify(), detect_publisher(), normalize_url(), test_detect_publisher(), test_entity_resolver_aliases(), test_normalize_url(), test_slugify()

## Ambiguous Edges - Review These
- `3D News Knowledge Graph HTML` → `Author Photo`  [AMBIGUOUS]
  photo.jpg · relation: references

## Knowledge Gaps
- **9 isolated node(s):** `Claude Command: Engagement Analytics`, `Claude Command: Visitor Trend`, `Claude Command: Visitor Summary`, `DriftForge Docker Compose`, `Robots Allow-All` (+4 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 124 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `GraphStore` connect `Graph Store API` to `Article Ingestion Pipeline`, `Graph Query Engine`, `FastAPI App Setup`, `SQLite Database Layer`, `Test Config & Fixtures`, `Data Models & Schemas`, `Entity Resolver & URL Normalization`?**
  _High betweenness centrality (0.195) - this node is a cross-community bridge._
- **Are the 27 inferred relationships involving `GraphStore` (e.g. with `Article` and `Conversation`) actually correct?**
  _`GraphStore` has 27 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Claude Command: Engagement Analytics`, `Claude Command: Visitor Trend`, `Claude Command: Visitor Summary` to the rest of the system?**
  _9 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Graph Store API` be split into smaller, more focused modules?**
  _Cohesion score 0.07591836734693877 - nodes in this community are weakly interconnected._
- **Why does `get_db()` connect `SQLite Database Layer` to `Graph Store API`, `Article Ingestion Pipeline`, `Graph Query Engine`, `FastAPI App Setup`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Article` (e.g. with `GraphStore` and `LLMExtractor`) actually correct?**
  _`Article` has 5 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `3D News Knowledge Graph HTML` and `Author Photo`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._