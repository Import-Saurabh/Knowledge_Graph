# Project Implementation Plan: Knowledge Graph & Intelligence Platform

## Executive Summary
This document outlines the architectural roadmap and daily development trajectory for the **Knowledge Graph & Intelligence Platform** (`Knowledge_Graph`).
The platform ingests multi-source global news streams, extracts entities and relationships with temporal provenance via large language models, persists them in an ACID-compliant graph store with FTS5 indexing, exposes an asynchronous REST API via FastAPI, and serves an interactive 3D WebGL visualization coupled with an evidence-backed conversational research workspace.

---

## 1. System Architecture

```
                               ┌────────────────────────────────────────┐
                               │                Browser                 │
                               │  ┌──────────────┐    ┌──────────────┐  │
                               │  │ 3D Graph     │◄──►│ Graph Chat   │  │
                               │  │ (index.html) │    │ (chat.html)  │  │
                               │  └──────┬───────┘    └──────┬───────┘  │
                               └─────────┼───────────────────┼──────────┘
                                         │ fetch             │ /api/query
                                         ▼                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application Server                      │
│                                                                        │
│   ┌────────────────┐   ┌────────────────┐   ┌──────────────────────┐   │
│   │ Graph Engine   │   │ Query Engine   │   │ Ingestion Pipeline   │   │
│   │ /api/graph     │   │ /api/query     │   │ /api/ingest          │   │
│   └───────┬────────┘   └───────┬────────┘   └──────────┬───────────┘   │
│           │                    │                       │               │
│           ▼                    ▼                       ▼               │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │              SQLite Persistent Knowledge Store (WAL)           │   │
│   │  - entities & aliases       - events & temporal metadata       │   │
│   │  - relationships (directed) - articles & URL deduplication     │   │
│   │  - claims & source evidence - conversations & message logs     │   │
│   │  - FTS5 Full-Text Search Indexes                               │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                │                                       │
│   ┌────────────────────────────┴───────────────────────────────────┐   │
│   │             APScheduler Background Ingestion Worker            │   │
│   │             (Autonomous hourly continuous sync)                │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│   External Services: MiniMax / Anthropic LLM API · RSS News Feeds      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Modules & Responsibilities

1. **Storage Layer (`server/database.py`, `server/models.py`)**:
   - SQLite with WAL mode (`PRAGMA journal_mode=WAL;`).
   - Tables: `entities`, `events`, `articles`, `claims`, `relationships`, `entity_event_links`, `conversations`, `messages`, `ingestion_jobs`.
   - FTS5 full-text search indexes for instant keyword matching across entities and events.
   - Pydantic v2 schemas for rigid type safety and serialisation.

2. **Ingestion Subsystem (`server/ingestion/`)**:
   - `sources.py`: Robust RSS feed parsing supporting multi-lingual publication formats and sanitization.
   - `extractor.py`: Structured prompt-engineering extracting entities, relationships, temporal context, and source quotes.
   - `resolver.py`: Slug normalization, alias matching, and entity deduplication to prevent graph fragmentation.
   - `writer.py`: Idempotent transactional upserts to SQLite ensuring no duplicate relationships.
   - `pipeline.py`: Unified pipeline orchestrator coordinating the ETL lifecycle.

3. **Query & Reasoning Engine (`server/query/`)**:
   - `retriever.py`: Multi-hop recursive graph traversal using SQL recursive CTEs.
   - `researcher.py`: Automated discovery and live news fetching when query coverage is stale.
   - `synthesizer.py`: Grounded multi-document summarization providing factual answers with source citations.
   - `engine.py`: Coordinates graph retrieval and LLM reasoning.

4. **REST API & Scheduling (`server/routes/`, `server/scheduler.py`, `server/app.py`)**:
   - FastAPI application serving both REST API endpoints and static visualization assets.
   - Background job runner powered by APScheduler with overlap prevention and persistent execution metrics.
   - Endpoints for graph visualization (`/api/graph`), entity details (`/api/entities/{id}`), conversational search (`/api/query`), and ingestion management (`/api/ingest`).

5. **Frontend Interfaces (`index.html`, `chat.html`)**:
   - `index.html`: Three.js / WebGL 3D force-directed knowledge graph with community clustering, camera transitions, and deep-link node highlighting (`?highlight=id`).
   - `chat.html`: ChatGPT-style workspace providing interactive multi-turn conversations with source citations, claim verification, and deep-linking into the 3D graph view.

6. **Quality Assurance & DevOps (`tests/`, `Dockerfile`, `docker-compose.yml`)**:
   - Unit and integration test suite (`pytest`) validating database transactions, entity resolution, and API endpoints.
   - Docker containerization for portable cloud and local deployment.

---

## 3. Detailed Development Schedule (Sept 1, 2026 – Oct 12, 2026)

| Date | Commit 1 (Implementation Focus) | Commit 2 (Iterative Bug Fix / Refactor) |
|---|---|---|
| **2026-09-01** | `feat: initialize repository and development plan` | `fix: adjust gitignore to exclude environment caches and bytecode` |
| **2026-09-02** | `feat: establish project dependency manifest` | `fix: pin pydantic and fastapi dependencies for compatibility` |
| **2026-09-03** | `docs: draft high-level architecture diagram` | `fix: correct Mermaid diagram arrow definitions for markdown renderers` |
| **2026-09-04** | `docs: add High-Level Design (HLD) specifications` | `fix: refine HLD data flow sequence and entity schema descriptions` |
| **2026-09-05** | `docs: add Low-Level Design (LLD) specifications` | `fix: clarify recursive CTE query specifications in LLD document` |
| **2026-09-06** | `feat: configure environment template and server settings` | `fix: ensure default database directory creation in configuration` |
| **2026-09-07** | `feat: implement SQLite database initialization and schemas` | `fix: enable WAL mode and foreign key constraints in database init` |
| **2026-09-08** | `feat: implement Pydantic domain models for graph entities` | `fix: add optional field defaults and JSON encoder in entity models` |
| **2026-09-09** | `feat: add FTS5 full-text search indexes for entities and events` | `fix: handle edge case in SQLite FTS5 table trigger updates` |
| **2026-09-10** | `feat: implement database migration runner and connection pool` | `fix: resolve database lock timeout during concurrent queries` |
| **2026-09-11** | `test: setup automated testing suite and database tests` | `fix: isolate test database file fixture with auto-cleanup` |
| **2026-09-12** | `feat: implement RSS feed connector for news ingestion` | `fix: sanitize HTML entities and handle invalid XML feed entries` |
| **2026-09-13** | `feat: add URL hashing and article deduplication logic` | `fix: normalize URLs by stripping UTM query parameters` |
| **2026-09-14** | `feat: implement LLM entity and relationship extraction module` | `fix: handle JSON extraction errors and format malformed responses` |
| **2026-09-15** | `feat: develop entity resolver with slug and alias matching` | `fix: prevent duplicate node links during entity resolution` |
| **2026-09-16** | `feat: implement transactional knowledge graph database writer` | `fix: correct upsert conflict resolution for relationship records` |
| **2026-09-17** | `feat: build ingestion pipeline orchestrator` | `fix: isolate feed errors so single source failure does not halt job` |
| **2026-09-18** | `test: add end-to-end ingestion pipeline tests` | `fix: mock LLM API calls in ingestion test suite` |
| **2026-09-19** | `feat: integrate APScheduler for autonomous background sync` | `fix: prevent overlapping job runs with execution lock flag` |
| **2026-09-20** | `feat: implement graph retriever with multi-hop CTE queries` | `fix: cap maximum traversal depth to prevent runaway CTE queries` |
| **2026-09-21** | `feat: add fresh news researcher for query-triggered ingestion` | `fix: respect research budget limits on high-frequency queries` |
| **2026-09-22** | `feat: develop LLM answer synthesizer with grounded citations` | `fix: format inline markdown citations and validate article sources` |
| **2026-09-23** | `feat: integrate unified query engine service` | `fix: resolve fallback response when no graph connections exist` |
| **2026-09-24** | `feat: create FastAPI application and middleware foundation` | `fix: configure CORS headers and custom request logging middleware` |
| **2026-09-25** | `feat: implement graph visualization REST endpoints` | `fix: optimize serialization performance for large graph payloads` |
| **2026-09-26** | `feat: implement entity details and subgraph API routes` | `fix: return 404 with structured error message for unknown entities` |
| **2026-09-27** | `feat: add conversational query and session endpoints` | `fix: validate session UUID format and handle missing session IDs` |
| **2026-09-28** | `feat: implement ingestion trigger and status reporting API` | `fix: enforce admin API key validation on trigger endpoint` |
| **2026-09-29** | `feat: add health check endpoint with database diagnostics` | `fix: return detailed service statuses in health response` |
| **2026-09-30** | `test: add comprehensive FastAPI integration test suite` | `fix: update test client headers to include test authentication token` |
| **2026-10-01** | `feat: add web assets and favicon metadata` | `fix: optimize SVG rendering and touch icon dimensions` |
| **2026-10-02** | `feat: establish baseline graph sample data` | `fix: reconcile orphaned node references in graph data` |
| **2026-10-03** | `feat: build 3D Three.js knowledge graph visualizer` | `fix: tweak camera damping and node label rendering performance` |
| **2026-10-04** | `feat: implement community clustering and sentiment link coloring` | `fix: resolve color palette mapping for neutral relationships` |
| **2026-10-05** | `feat: implement entity search and auto-focus camera framing` | `fix: handle edge cases when searching special characters in 3D graph` |
| **2026-10-06** | `feat: develop Graph Chat conversational workspace interface` | `fix: adjust mobile chat input responsiveness and auto-scroll behavior` |
| **2026-10-07** | `feat: integrate chat workspace with backend query API` | `fix: format streaming citation cards and source link clicks` |
| **2026-10-08** | `feat: implement bidirectional deep linking between Chat and 3D Graph` | `fix: ensure highlighted nodes pulse and auto-dim unrelated graph nodes` |
| **2026-10-09** | `feat: add containerization support with Dockerfile and Compose` | `fix: streamline multi-stage Docker build to minimize image size` |
| **2026-10-10** | `feat: integrate codebase call flow and architectural reports` | `fix: update relative asset paths in static analysis HTML report` |
| **2026-10-11** | `docs: document implementation roadmap and production milestones` | `fix: verify test coverage across all 15 test suites and update docs` |
| **2026-10-12** | `docs: finalize production documentation and deployment guide` | `refactor: clean up comments and polish production configuration` |

---

## 4. Verification & Testing Checklist

- [x] **Database Integrity**: SQLite tables, foreign keys, and FTS5 tables functional in WAL mode.
- [x] **Ingestion Accuracy**: News articles parsed, deduplicated, and entities extracted with provenance.
- [x] **Graph Traversal**: Multi-hop queries retrieve connected subgraphs efficiently.
- [x] **Chat Experience**: Conversational answers backed by explicit source citations.
- [x] **Visual Integration**: Deep linking (`?highlight=...`) reliably frames target nodes in 3D WebGL view.
- [x] **Automated Tests**: All 15 unit and integration tests passing (`tests/test_api.py`, `tests/test_database.py`, `tests/test_ingestion.py`).
- [x] **Containerization**: Validated Dockerfile and docker-compose configurations.
