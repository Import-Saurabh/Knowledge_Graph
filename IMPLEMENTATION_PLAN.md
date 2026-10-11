# IMPLEMENTATION PLAN — DriftForge News Intelligence Platform

> **Status**: Complete — All 11 phases implemented and verified. Production server active.
> **Created**: 2026-10-11
> **Last Updated**: 2026-10-11

---

## 1. Project Audit

### 1.1 Current Architecture

DriftForge is a **serverless static website** with a separate batch pipeline. There is **no backend API server**.

```
Architecture:
  EventBridge (cron) → Lambda (pipeline.py) → RSS feeds + LLM → graph.json → S3
  S3 → CloudFront → Browser (index.html loads graph.json via fetch)
  CloudFront logs → S3 → Lambda (cf_log_shipper.py) → CloudWatch + SNS
```

### 1.2 Existing Files and Their Roles

| File | Role |
|---|---|
| `index.html` | Single-file frontend: 3D force graph (Three.js/WebGL), toolbar, filters, search, side panel, about modal. ~1579 lines, no build step. Loads `graph.json` via `fetch('graph.json')`. |
| `pipeline.py` | Data pipeline: fetch RSS → LLM extraction → build graph.json → upload S3. Runs as Lambda or CLI. |
| `cf_log_shipper.py` | Lambda: parses CloudFront access logs, ships to CloudWatch, alerts on new visitors via SNS. |
| `make_og_image.py` | Utility: generates Open Graph social preview image. |
| `graph.json` | Generated data: flat JSON with `nodes[]` and `links[]`. Completely rebuilt each run. |
| `requirements.txt` | Python deps: anthropic, feedparser, pydantic, boto3, python-dotenv, graphifyy. |
| `architecture.md` | Mermaid diagram of AWS architecture. |
| `.github/workflows/deploy.yml` | CI/CD: uploads static files to S3, invalidates CloudFront. |
| `.claude/commands/` | Claude Code slash commands for CloudWatch log queries. |
| `graphify-out/` | Graphify codebase analysis artifacts (preserved, read-only). |

### 1.3 Current Ingestion and Graph-Generation Flow

1. `pipeline.py:fetch_articles()` — fetches from 6 RSS feeds (BBC, NPR, Guardian, Al Jazeera, DW, France24), max 4 articles per feed.
2. `pipeline.py:extract_graph()` — sends article titles+summaries to LLM (MiniMax-M3 via Anthropic SDK), receives structured JSON with entities and relationships.
3. `pipeline.py:build_graph()` — validates references, filters broken links, builds `{nodes, links}`.
4. `pipeline.py:main()` — orchestrates fetch→extract→build→write→upload.
5. `pipeline.py:lambda_handler()` — wraps `main()` with quiet-hours/idle checks for Lambda.

### 1.4 Current Graph Schema

**Entity types**: `person | organisation | country | event | concept`

**Relationship types**: `causes | caused_by | involves | opposes | supports | allies_with | threatens | located_in | responds_to | impacts | negotiates_with | accuses | sanctions`

**Node properties**: `id`, `label`, `type`, `description`
**Link properties**: `source`, `target`, `type`, `description`
**Graph metadata**: `generated_at` (ISO timestamp)

**No temporal data on nodes/links. No article references. No evidence provenance. No stable IDs across runs.**

### 1.5 Existing Persistence

**None.** `graph.json` is the only data store. It is completely rebuilt on every pipeline run. No database. No historical data preservation.

### 1.6 Existing UI Structure

Single HTML page with:
- 3D force graph (full viewport)
- Top toolbar: title, subtitle, stats, search, filter buttons, community/sentiment toggles, version badge, about button
- Side panel: entity details, connections list
- Loading screen with animated network graphic
- Flyover tour on first visit
- Auto-refresh every 5 minutes
- Mobile-optimized touch controls
- About modal with author info

**No routing. No sidebar. No navigation between pages. No chat interface.**

### 1.7 Relevant Graphify Findings

From `.graphify_analysis.json`:
- **7 communities** detected across 35 code nodes
- **"God" functions** (highest degree): `cf_log_shipper.lambda_handler()` (degree 9), `pipeline.main()` (degree 7)
- **Key bridge edges**: `main()→fetch_articles()`, `main()→extract_graph()`, `lambda_handler()→parse_line()`, `lambda_handler()→load_known_ips()`
- `pipeline.py` and `cf_log_shipper.py` are independent modules with no shared code
- `make_og_image.py` is isolated (community 4)

### 1.8 Known Limitations and Technical Debt

1. **No persistence** — graph is rebuilt from scratch each run, losing all history
2. **No backend API** — frontend has no server to query, cannot support chat or interactive queries
3. **No entity resolution** — same entity may get different IDs across pipeline runs
4. **No article storage** — source articles are not retained after extraction
5. **No evidence provenance** — claims cannot be traced to specific articles
6. **No temporal data** — events lack timestamps, no timeline capability
7. **No deduplication** — duplicate articles from syndication not detected
8. **No tests** — zero automated tests
9. **No authentication** — all endpoints are public
10. **Hardcoded AWS resources** — S3 bucket names, SNS ARNs, CloudFront IDs in source code

---

## 2. Target Architecture

### 2.1 Architecture Overview

Transform from serverless-static to a **Python backend application** with persistent storage, while preserving the existing frontend.

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ 3D Graph     │  │ Graph Chat   │  │ Navigation       │   │
│  │ (existing)   │  │ (new)        │  │ Sidebar (new)    │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘   │
│         │                 │                                  │
│         └────────┬────────┘                                  │
│                  │ fetch /api/*                               │
└──────────────────┼───────────────────────────────────────────┘
                   │
┌──────────────────┼───────────────────────────────────────────┐
│           FastAPI Backend (new)                               │
│  ┌────────┐ ┌─────────┐ ┌───────────┐ ┌────────────────┐    │
│  │ Graph  │ │ Query   │ │ Ingestion │ │ Static Files   │    │
│  │ API    │ │ Engine  │ │ API       │ │ (index.html)   │    │
│  └───┬────┘ └────┬────┘ └─────┬─────┘ └────────────────┘    │
│      │           │            │                              │
│  ┌───┴───────────┴────────────┴──────────────────────────┐   │
│  │              Service Layer                             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │
│  │  │ Ingestion│ │ Entity   │ │ Graph    │ │ Research │ │   │
│  │  │ Pipeline │ │ Resolver │ │ Store    │ │ Engine   │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │   │
│  └───────────────────────┬───────────────────────────────┘   │
│                          │                                    │
│  ┌───────────────────────┼───────────────────────────────┐   │
│  │         SQLite + FTS5 (persistent storage)             │   │
│  │  entities | events | articles | claims | relationships │   │
│  │  conversations | messages | ingestion_jobs              │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐   │
│  │      APScheduler (background ingestion worker)          │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                               │
│  External: MiniMax LLM API, RSS Feeds                         │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 Key Architecture Decisions

| Decision | Rationale |
|---|---|
| **FastAPI** as backend | Lightweight, async-capable, typed, auto-docs. Proportional to project size. Serves both API and existing static files. |
| **SQLite + FTS5** instead of Neo4j | The project is a single-developer app with modest data volume. Neo4j adds operational complexity (JVM, separate service, Docker). SQLite provides persistence, ACID transactions, full-text search, and zero-ops. Graph traversal queries are implementable via recursive CTEs. If data volume grows, migration path to PostgreSQL is straightforward. |
| **APScheduler** for background jobs | In-process scheduler avoids separate worker service. Configurable, persistent job store in SQLite. Sufficient for hourly/daily ingestion. |
| **Single process** | API + scheduler in one process. Appropriate for the traffic level. No distributed coordination needed. |
| **Preserve index.html** | Served as static file by FastAPI. Modified only to add sidebar navigation and Graph Chat page. No framework migration. |

### 2.3 Why Not Neo4j

Neo4j was evaluated per the requirements. Reasons for choosing SQLite instead:

1. **Operational complexity**: Neo4j requires a JVM, separate process, Docker, and 512MB+ RAM. Disproportionate for this project.
2. **Data volume**: Expected <100K entities, <500K relationships. Well within SQLite's capability.
3. **Graph queries**: Multi-hop traversal is achievable via recursive CTEs in SQLite. The query patterns needed (2-3 hop neighborhood retrieval, entity lookup, time-bounded queries) don't require a native graph query language.
4. **Deployment simplicity**: SQLite is a file — no separate service, no connection management, no Docker dependency.
5. **Migration path**: If graph complexity grows, PostgreSQL with Apache AGE extension or Neo4j can be introduced. The data access layer will use an abstraction that makes this feasible.

---

## 3. Database and Data Model

### 3.1 Schema

```sql
-- Entities (persons, organizations, countries, etc.)
CREATE TABLE entities (
    id TEXT PRIMARY KEY,              -- stable slug: "united-nations"
    entity_type TEXT NOT NULL,        -- person|organisation|country|location|government|...
    canonical_name TEXT NOT NULL,
    description TEXT,
    aliases TEXT,                     -- JSON array of alternate names
    external_ids TEXT,                -- JSON object of external identifiers
    first_observed_at TEXT NOT NULL,  -- ISO timestamp
    updated_at TEXT NOT NULL,
    metadata TEXT                     -- JSON object for extensible properties
);

-- Events (military strikes, diplomatic meetings, etc.)
CREATE TABLE events (
    id TEXT PRIMARY KEY,              -- stable slug: "2026-10-11-saudi-strike"
    event_type TEXT NOT NULL,         -- military_strike|diplomatic_meeting|...
    summary TEXT NOT NULL,
    event_time TEXT,                  -- ISO timestamp or date (may be approximate)
    event_time_precision TEXT,        -- "exact"|"day"|"week"|"approximate"
    location TEXT,
    status TEXT DEFAULT 'reported',   -- reported|confirmed|denied|retracted
    confidence REAL DEFAULT 0.5,
    first_observed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT
);

-- Articles / Sources
CREATE TABLE articles (
    id TEXT PRIMARY KEY,              -- UUID
    url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL,           -- SHA-256 of normalized URL
    publisher TEXT,
    headline TEXT,
    summary TEXT,
    content_excerpt TEXT,             -- first ~500 chars or permitted excerpt
    content_hash TEXT,                -- SHA-256 of content for dedup
    author TEXT,
    language TEXT DEFAULT 'en',
    published_at TEXT,                -- ISO timestamp
    ingested_at TEXT NOT NULL,
    feed_source TEXT,                 -- which RSS feed discovered this
    extraction_status TEXT DEFAULT 'pending', -- pending|extracted|failed|skipped
    metadata TEXT
);

-- Claims / Evidence
CREATE TABLE claims (
    id TEXT PRIMARY KEY,              -- UUID
    claim_text TEXT NOT NULL,
    subject_entity_id TEXT,           -- FK to entities
    predicate TEXT,                   -- what is being claimed
    object_entity_id TEXT,            -- FK to entities
    source_article_id TEXT NOT NULL,  -- FK to articles
    attribution TEXT,                 -- who made the claim
    claim_type TEXT DEFAULT 'media_report', -- official_claim|media_report|corroborated
    confidence REAL DEFAULT 0.5,
    event_id TEXT,                    -- FK to events (if claim is about an event)
    observed_at TEXT NOT NULL,
    metadata TEXT,
    FOREIGN KEY (source_article_id) REFERENCES articles(id),
    FOREIGN KEY (subject_entity_id) REFERENCES entities(id),
    FOREIGN KEY (object_entity_id) REFERENCES entities(id),
    FOREIGN KEY (event_id) REFERENCES events(id)
);

-- Relationships (entity-to-entity, entity-to-event, etc.)
CREATE TABLE relationships (
    id TEXT PRIMARY KEY,              -- UUID
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,  -- PARTICIPATED_IN, LOCATED_IN, etc.
    description TEXT,
    source_article_id TEXT,           -- FK to articles (provenance)
    first_observed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT,
    UNIQUE(source_id, target_id, relationship_type)
);

-- Entity-Event participation
CREATE TABLE entity_event_links (
    entity_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    role TEXT,                        -- participant|target|location|actor
    source_article_id TEXT,
    PRIMARY KEY (entity_id, event_id, role),
    FOREIGN KEY (entity_id) REFERENCES entities(id),
    FOREIGN KEY (event_id) REFERENCES events(id)
);

-- Conversations (Graph Chat)
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Messages
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,               -- user|assistant
    content TEXT NOT NULL,
    citations TEXT,                   -- JSON array of citation objects
    entity_ids TEXT,                  -- JSON array of referenced entity IDs
    event_ids TEXT,                   -- JSON array of referenced event IDs
    research_metadata TEXT,           -- JSON: sources searched, articles found, etc.
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- Ingestion Jobs
CREATE TABLE ingestion_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,           -- scheduled|manual|query_triggered
    status TEXT NOT NULL,             -- running|completed|failed|cancelled
    started_at TEXT NOT NULL,
    completed_at TEXT,
    trigger TEXT,                     -- "scheduler"|"api"|"query:xxx"
    articles_discovered INTEGER DEFAULT 0,
    articles_processed INTEGER DEFAULT 0,
    articles_skipped INTEGER DEFAULT 0,
    articles_failed INTEGER DEFAULT 0,
    entities_created INTEGER DEFAULT 0,
    entities_updated INTEGER DEFAULT 0,
    events_created INTEGER DEFAULT 0,
    relationships_created INTEGER DEFAULT 0,
    error_details TEXT,
    metadata TEXT
);
```

### 3.2 Indexes

```sql
CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_name ON entities(canonical_name);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_time ON events(event_time);
CREATE INDEX idx_articles_url_hash ON articles(url_hash);
CREATE INDEX idx_articles_publisher ON articles(publisher);
CREATE INDEX idx_articles_published_at ON articles(published_at);
CREATE INDEX idx_articles_content_hash ON articles(content_hash);
CREATE INDEX idx_claims_subject ON claims(subject_entity_id);
CREATE INDEX idx_claims_event ON claims(event_id);
CREATE INDEX idx_relationships_source ON relationships(source_id);
CREATE INDEX idx_relationships_target ON relationships(target_id);
CREATE INDEX idx_relationships_type ON relationships(relationship_type);
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_ingestion_jobs_status ON ingestion_jobs(status);

-- Full-text search
CREATE VIRTUAL TABLE entities_fts USING fts5(
    canonical_name, description, aliases,
    content=entities, content_rowid=rowid
);
CREATE VIRTUAL TABLE events_fts USING fts5(
    summary, location,
    content=events, content_rowid=rowid
);
```

### 3.3 Deduplication Strategy

- **Articles**: URL normalization + SHA-256 hash. `UNIQUE(url)` constraint. Content hash for detecting same content at different URLs.
- **Entities**: Slug-based IDs (`united-nations`). Alias matching during resolution. Conservative merge — prefer keeping entities separate over false merges.
- **Events**: Time + location + entity overlap heuristic. New articles about existing events add evidence rather than creating duplicates.
- **Relationships**: `UNIQUE(source_id, target_id, relationship_type)` constraint. Upsert on conflict.

---

## 4. API Design

### 4.1 Endpoints

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET /` | Serve index.html (existing 3D graph) | None |
| `GET /chat` | Serve Graph Chat page | None |
| `GET /api/health` | Health check with DB status | None |
| `GET /api/graph` | Graph data for 3D visualization | None |
| `GET /api/graph/subgraph` | Subgraph around specific node IDs | None |
| `GET /api/entities/{id}` | Entity details + relationships | None |
| `GET /api/events/{id}` | Event details + evidence | None |
| `GET /api/entities/search` | Search entities by name/alias | None |
| `POST /api/query` | Graph Chat: research + answer | None |
| `POST /api/conversations` | Create new conversation | None |
| `GET /api/conversations` | List conversations | None |
| `GET /api/conversations/{id}` | Get conversation with messages | None |
| `POST /api/ingest` | Trigger manual ingestion | API key |
| `GET /api/ingestion/status` | Ingestion job history | None |

### 4.2 Key Request/Response Contracts

**POST /api/query**
```json
// Request
{
  "question": "What are today's major Saudi Arabia-Houthi developments?",
  "conversation_id": "optional-uuid",
  "timezone": "Asia/Kolkata"
}

// Response
{
  "answer": "## Major Developments\n\n...",
  "citations": [
    {
      "id": "article-uuid",
      "headline": "Saudi forces intercept Houthi drone",
      "publisher": "Al Jazeera",
      "url": "https://...",
      "published_at": "2026-10-11T10:00:00Z"
    }
  ],
  "entity_ids": ["saudi-arabia", "houthi-movement"],
  "event_ids": ["2026-10-11-drone-intercept"],
  "research_metadata": {
    "sources_searched": 6,
    "articles_found": 12,
    "articles_new": 3,
    "research_triggered": true,
    "reporting_period": "2026-10-10 to 2026-10-11",
    "limitations": ["France24 feed unavailable"]
  },