# DriftForge — Persistent News Knowledge Graph & Graph Chat

DriftForge is a production-grade, continuously updated, evidence-backed news intelligence platform. It features an interactive **3D Knowledge Graph** visualization and a conversational **Graph Chat** workspace powered by Graph Retrieval-Augmented Generation (Graph RAG).

## Demo Walkthrough

Watch the complete demonstration showcasing the interactive 3D Knowledge Graph, real-time entity navigation, and evidence-grounded Graph Chat:

🎬 **[Stream / Watch Demo Video](https://media.githubusercontent.com/media/Import-Saurabh/Knowledge_Graph/main/Media/Screen%20Recording%202026-10-12%20161635.mp4)** · **[View in Repository](Media/Screen%20Recording%202026-10-12%20161635.mp4)**

> 📹 **Direct Media Stream / Download**: [Click here to stream the full walkthrough MP4](https://media.githubusercontent.com/media/Import-Saurabh/Knowledge_Graph/main/Media/Screen%20Recording%202026-10-12%20161635.mp4)  
> 📁 **Repository Path**: [`Media/Screen Recording 2026-10-12 161635.mp4`](Media/Screen%20Recording%202026-10-12%20161635.mp4) *(tracked via Git LFS, 208 MB)*

---

## Table of Contents
1. [Demo Walkthrough](#demo-walkthrough)
2. [Architecture Overview](#architecture-overview)
3. [Setup & Installation Guide](#setup--installation-guide)
   - [Prerequisites](#prerequisites)
   - [Local Environment Setup](#local-environment-setup)
   - [Configuration & Environment Variables](#configuration--environment-variables)
   - [Running the Server](#running-the-server)
   - [Testing the Application](#testing-the-application)
   - [Docker Deployment](#docker-deployment)
4. [How the Knowledge Graph Works](#how-the-knowledge-graph-works)
   - [Persistent Data Model (SQLite WAL)](#persistent-data-model-sqlite-wal)
   - [Entity Resolution & Deduplication](#entity-resolution--deduplication)
   - [3D Interactive Visualization (WebGL/Three.js)](#3d-interactive-visualization-webglthreejs)
   - [Community Detection & Link Sentiment](#community-detection--link-sentiment)
   - [Targeted Node Search & Camera Flight](#targeted-node-search--camera-flight)
5. [How the News Ingestion Pipeline Works](#how-the-news-ingestion-pipeline-works)
   - [RSS News Harvesting](#rss-news-harvesting)
   - [Ingestion Basis: Titles vs. Content Summaries](#ingestion-basis-titles-vs-content-summaries)
   - [URL Normalization & Deduplication](#url-normalization--deduplication)
   - [LLM Knowledge Extraction](#llm-knowledge-extraction)
   - [Transactional Persistence & Snapshot Export](#transactional-persistence--snapshot-export)
   - [Ingestion Triggers: Scheduled, Manual & Query-Driven](#ingestion-triggers-scheduled-manual--query-driven)
6. [How Graph Chat Works](#how-graph-chat-works)
   - [Session & Multi-Turn State](#session--multi-turn-state)
   - [Entity Extraction & Multi-Hop Traversal](#entity-extraction--multi-hop-traversal)
   - [On-Demand Wire News Discovery](#on-demand-wire-news-discovery)
   - [Evidence-Grounded Synthesis & Citations](#evidence-grounded-synthesis--citations)
   - [Deep Linking from Chat into the 3D Graph](#deep-linking-from-chat-into-the-3d-graph)
7. [API Reference](#api-reference)
8. [Database Backup & Maintenance](#database-backup--maintenance)

---

## Architecture Overview

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
│   │             (Harvests hourly news updates autonomously)        │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│   External Services: MiniMax / Anthropic LLM API · Global RSS Feeds    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Setup & Installation Guide

### Prerequisites
- **Python**: Version 3.10, 3.11, or 3.12
- **Operating System**: Windows, macOS, or Linux
- **LLM API Key**: Anthropic API Key or MiniMax API Key (Anthropic-compatible endpoint)

---

### Local Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Import-Saurabh/Knowledge_Graph.git
   cd Knowledge_Graph
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**:
   - **Windows PowerShell**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Windows Command Prompt (cmd)**:
     ```cmd
     .\.venv\Scripts\activate.bat
     ```
   - **macOS / Linux**:
     ```bash
     source .venv/bin/activate
     ```

4. **Install Python dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

### Configuration & Environment Variables

Create a `.env` file in the root directory by copying the example template:
```bash
cp .env.example .env
```

Configure the environment variables according to your setup:

| Variable | Default Value | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Network interface to bind the FastAPI server. |
| `PORT` | `8080` | Local port number for HTTP access. |
| `DATABASE_PATH` | `data/driftforge.db` | Path to the persistent SQLite database file. |
| `ANTHROPIC_BASE_URL` | `https://api.minimax.io/anthropic` | LLM API base URL. Use default for MiniMax or omit for native Anthropic. |
| `ANTHROPIC_API_KEY` | *(Required)* | API key for Anthropic or MiniMax. Can also be set via `MINIMAX_API_KEY`. |
| `LLM_MODEL` | `MiniMax-M3` | Model identifier (e.g. `MiniMax-M3`, `claude-3-7-sonnet-20250219`). |
| `LLM_TIMEOUT` | `60` | Request timeout in seconds for LLM extraction and synthesis. |
| `ADMIN_API_KEY` | `driftforge-admin-secret` | Security token for manual ingestion (`POST /api/ingest`). |
| `SCHEDULER_ENABLED` | `true` | When `true`, activates background hourly news ingestion. |
| `INGESTION_SCHEDULE_HOURS`| `1` | Interval (in hours) between autonomous RSS ingestion runs. |
| `MAX_ARTICLES_PER_FEED` | `4` | Maximum articles to pull per RSS feed during routine ingestion. |
| `TIMEZONE` | `UTC` | Timezone for scheduler execution logs. |

---

### Running the Server

Start the development server with hot-reload enabled:

- **Windows PowerShell**:
  ```powershell
  .\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
  ```

- **macOS / Linux**:
  ```bash
  uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
  ```

Once running, access the services:
- **3D Knowledge Graph**: [http://localhost:8080/](http://localhost:8080/)
- **Graph Chat Workspace**: [http://localhost:8080/chat](http://localhost:8080/chat)
- **Interactive OpenAPI Documentation (Swagger UI)**: [http://localhost:8080/docs](http://localhost:8080/docs)
- **System Health Endpoint**: [http://localhost:8080/api/health](http://localhost:8080/api/health)

---

### Testing the Application

Execute the automated test suite covering SQLite initialization, FTS5 search, RSS parsing, entity resolution, and route authorization:

```bash
# Windows:
.\.venv\Scripts\pytest.exe -v

# macOS/Linux:
pytest -v
```

---

### Docker Deployment

To build and launch the platform with Docker Compose:

```bash
docker compose up -d --build
```

View live application logs:
```bash
docker compose logs -f driftforge
```

---

## How the Knowledge Graph Works

### Persistent Data Model (SQLite WAL)
Unlike memory-only or transient graph visualizers, DriftForge persists all entities, relationships, events, and evidence in **SQLite** with Write-Ahead Logging (`PRAGMA journal_mode=WAL`). This gives concurrent read/write performance, ACID durability, and fast query execution.

The core schema comprises:
- **`entities`**: Unique actors (`id`, `entity_type`, `canonical_name`, `description`, `aliases`, `first_observed_at`, `updated_at`).
- **`relationships`**: Directed edges (`id`, `source_id`, `target_id`, `relationship_type`, `description`, `source_article_id`, `first_observed_at`).
- **`events`**: Discrete real-world occurrences (`id`, `event_type`, `summary`, `event_time`, `location`, `participants`).
- **`claims`**: Concrete factual assertions extracted from reporting (`claim_text`, `subject_entity_id`, `predicate`, `object_entity_id`, `attribution`, `source_article_id`).
- **`articles`**: Ingested news items (`url`, `url_hash`, `publisher`, `headline`, `summary`, `published_at`).
- **`entities_fts` & `events_fts`**: SQLite FTS5 full-text search virtual tables enabling sub-millisecond keyword lookup over names, aliases, summaries, and descriptions.

On first boot, the system automatically initializes the schema and seeds baseline knowledge from `graph.json` if the database is empty.

---

### Entity Resolution & Deduplication
To prevent entity fragmentation (e.g. creating distinct nodes for *"BBC"*, *"BBC News"*, and *"British Broadcasting Corporation"*), the ingestion layer applies an automated **Entity Resolver**:
1. **Slug Normalization**: Converts labels to lowercased, hyphen-separated identifiers (e.g. `narendra-modi`, `delhi-police`).
2. **Alias Matching**: Checks incoming names against existing canonical names and alias arrays in the database.
3. **Idempotent Upserting**: If an entity already exists, its alias set is merged, its description is updated with fresh context, and its `updated_at` timestamp is renewed—without duplicating the node.

---

### 3D Interactive Visualization (WebGL/Three.js)
The frontend (`index.html`) renders the graph as an interactive WebGL 3D network powered by `3d-force-graph` and `three-spritetext`:
- **Force Simulation**: A physics engine balances node repulsion (`charge: -400`) and relationship pull (`link distance: 80`) to naturally group related entities into spatial clusters.
- **Connectivity Scaling**: Nodes scale in size quadratically based on their degree of connection:
  $$\text{val} = \max(4, \text{degree}^2 + 4)$$
  High-influence entities (world leaders, major nations, key organizations) naturally appear larger, while niche entities remain compact.
- **Dynamic Label Sprites**: Each node displays an oriented text sprite billboard that automatically angles away from adjacent neighbors to prevent overlapping clutter.

---

### Community Detection & Link Sentiment
- **Unsupervised Community Detection**: Built-in Label Propagation partitions the graph into topical clusters (e.g., European diplomacy, Middle Eastern conflicts, Tech/AI policy). Toggling **Community colours** assigns distinct palette colors to each detected cluster.
- **Sentiment & Relationship Links**:
  - **Hostile Links** (e.g., `opposes`, `threatens`, `sanctions`, `causes`): Highlighted in vivid red/orange.
  - **Cooperative Links** (e.g., `allies_with`, `supports`, `negotiates_with`): Rendered in emerald green/cyan.
  - **Neutral Links** (e.g., `involves`, `located_in`, `impacts`): Displayed in slate gray.
- **Particle Flows**: Animated directional particles travel along links to indicate relationship directionality and active connectivity.

---

### Targeted Node Search & Camera Flight
The search system in `index.html` provides precision navigation in 3D:
1. **Live Search**: As you type, a dropdown lists matching entities with their type, connection count, and color indicator.
2. **Immediate 3D Camera Flight**: Selecting an entity (or pressing <kbd>Enter</kbd>) smoothly animates the camera directly to that exact node in 3D space (`G.cameraPosition(...)`), placing it front-and-center at a calibrated viewing distance (`dist = 130`).
3. **Connecting Node Illumination (No Dimming of Connections)**:
   - The selected entity and **all of its directly connected neighbors** remain in **full, vibrant color**.
   - All relationship links connecting the selected entity to its neighbors remain brightly colored with accelerated particle streams.
   - Entity labels for the selected node and its connecting neighbors are rendered in prominent white text.
   - Unconnected background nodes in the distance are subdued to remove visual noise while preserving local context.
4. **Radiant Pulse Rings**: The target node emits expanding geometric pulse rings in 3D space to immediately signal its location.
5. **Context Side Panel**: Opens automatically to show the entity's type, background summary, and interactive list of connected entities.

---

## How the News Ingestion Pipeline Works

### RSS News Harvesting
DriftForge continuously harvests headlines from leading international wire services and public broadcasters:
- **BBC News World**: `http://feeds.bbci.co.uk/news/world/rss.xml`
- **NPR News**: `https://feeds.npr.org/1001/rss.xml`
- **The Guardian World**: `https://www.theguardian.com/world/rss`
- **Al Jazeera English**: `https://www.aljazeera.com/xml/rss/all.xml`
- **Deutsche Welle (DW)**: `https://rss.dw.com/rdf/rss-en-world`
- **France 24**: `https://www.france24.com/en/rss`

Feeds are fetched concurrently using a thread pool. Each source is wrapped in isolated error handlers so that a single feed timeout or network hiccup never interrupts other sources.

---

### Ingestion Basis: Titles vs. Content Summaries

A frequent question is: **How are news items processed? Does the system read titles, full bodies, or summaries?**

DriftForge extracts knowledge on the basis of **both Headline Titles and Content Summaries/Excerpts**:

1. **Headline Titles (`headline`)**:
   - Provide the primary anchor for the event or development.
   - Used for quick entity identification and high-level subject-action-object framing (e.g., *"Activists Detained Ahead of Planned March"*).
2. **Content Summaries & Excerpts (`summary` / `content_excerpt`)**:
   - RSS feeds supply paragraph-length editorial summaries or lead paragraphs (150–500 characters).
   - This body text contains the evidentiary nuance: specific quotes, government ministry attributions, locations, background reasons, and secondary participants that are absent from short headlines alone.
3. **Combined Feed Payload**:
   During extraction, each article is packaged for the LLM as:
   ```text
   ARTICLE 1 (BBC News - 2026-10-12):
   Title: Activists Detained in Delhi Amid Planned Demonstration
   Summary: Delhi police confirmed the preventative detention of CJP founder Abhijeet Dipke and other organizers ahead of the scheduled demonstration outside the ministry building.
   URL: https://www.bbc.com/news/world-asia-12345678
   ```
   This dual input provides high-density context without blowing through LLM token limits or risking web crawler bot-blocks.

---

### URL Normalization & Deduplication
To ensure articles are never re-processed redundantly:
1. **URL Normalization**: Strips marketing and tracking parameters (`utm_source`, `utm_medium`, `utm_campaign`, `fbclid`, `gclid`, `ref`, etc.) and normalizes schemes and hostnames.
2. **Cryptographic Hashing**:
   - Computes `url_hash = SHA256(clean_url)`
   - Computes `content_hash = SHA256(headline + "\n" + summary)`
3. **Deduplication Check**: Before calling the LLM, the pipeline checks `GraphStore.article_exists_by_url(url)`. If an article's normalized URL has already been recorded, it is skipped (`job.articles_skipped += 1`).

---

### LLM Knowledge Extraction
Unprocessed articles are sent in batches to the LLM (MiniMax M3 or Anthropic Claude) with a rigorous geopolitical analyst system prompt. The model responds strictly with structured JSON containing:
- **Entities**: Classified into `person`, `organisation`, `country`, `location`, `government`, `armed_group`, `concept`.
- **Events**: Categorized into `military_action`, `diplomatic_meeting`, `agreement`, `statement`, `sanctions`, `incident`, `economic_action`, `legal_action`. Includes timestamp and location.
- **Relationships**: Directed connections with types like `causes`, `opposes`, `supports`, `threatens`, `participated_in`, `located_in`, etc.
- **Claims**: Verifiable factual statements paired with source attribution and direct mapping to the originating article (`article_index`).

---

### Transactional Persistence & Snapshot Export
Once the LLM returns the extraction:
1. `GraphWriter` executes a transactional write into SQLite:
   - Inserts newly discovered articles.
   - Resolves and updates entities and aliases.
   - Records discrete events.
   - Creates directed relationships.
   - Stores evidentiary claims with article attribution.
2. `GraphWriter.export_graph_snapshot()` queries the latest SQLite state and writes an updated `graph.json` file. This allows static visualizer instances, cached endpoints, and fallback consumers to receive real-time graph updates without delay.

---

### Ingestion Triggers: Scheduled, Manual & Query-Driven
Ingestion can be initiated in three ways:
1. **Autonomous Scheduled Ingestion**: `APScheduler` runs hourly in the background (configurable via `INGESTION_SCHEDULE_HOURS`), fetching fresh feed updates.
2. **Manual Admin API**: Administrators can trigger ingestion on-demand via `POST /api/ingest` (secured by `X-API-Key: ADMIN_API_KEY`).
3. **Query-Triggered Wire Research**: When a user asks Graph Chat about an emerging entity or topic not found in the local graph, the system automatically runs live news wire discovery (see below).

---

## How Graph Chat Works

Graph Chat (`/chat`) is a conversational intelligence interface built on top of the knowledge graph. Rather than relying on generic, ungrounded LLM generation, Graph Chat uses **Graph RAG (Graph Retrieval-Augmented Generation)** to anchor answers in verified graph nodes, relationships, and published reporting.

---

### Session & Multi-Turn State
- Users can create and switch between conversation sessions.
- All conversations, user prompts, assistant briefings, cited entity IDs, and source links are persisted in SQLite (`conversations` and `messages` tables).
- Conversation history is preserved across browser refreshes and server restarts.

---

### Entity Extraction & Multi-Hop Traversal
When a user submits a question (e.g. *"What are the recent developments regarding Abhijeet Dipke and CJP?"*):
1. **Entity Identification**: `GraphRetriever` analyzes the question text against SQLite entities using both token matching and full-text search (`entities_fts`), resolving identified actors to their graph IDs (`abhijeet-dipke`, `cjp`).
2. **Multi-Hop Subgraph Traversal**:
   - Retrieves the 1-hop and 2-hop neighborhood of all identified entities.
   - Extracts all directed relationships connecting these actors to other entities.
   - Gathers associated events, recorded timestamps, and locations.
   - Retrieves attributed claims and verified source articles.

---

### On-Demand Wire News Discovery
If the user asks about a breaking event or entity that does not yet exist in the local graph (or checks **Force Live News Research** in the UI):
1. `QueryResearcher` detects that zero matching entities exist in SQLite.
2. It generates search queries and queries **Google News RSS search wire** (`https://news.google.com/rss/search?q=...`) to harvest live wire articles.
3. The LLM extracts entities, relationships, events, and claims from these newly discovered articles.
4. The extraction is immediately saved into SQLite, expanding the persistent knowledge base in real time.
5. The query engine re-queries the newly created subgraph and incorporates the fresh intelligence directly into the answer.

---

### Evidence-Grounded Synthesis & Citations
`AnswerSynthesizer` compiles the retrieved graph subgraph, events, claims, source articles, and conversation history into an evidence briefing for the LLM.

The resulting response contains:
- **Comprehensive Briefing**: A multi-paragraph analytical summary explaining relationships, causes, and impacts.
- **Explicit Entity Citations**: References to entities involved in the events.
- **Verified Source Citations**: Numbered references with publisher names and direct links to the articles (e.g. `[1] BBC News - Activists Detained in Delhi`).

---

### Deep Linking from Chat into the 3D Graph
Every response in Graph Chat is visually bridged to the 3D Knowledge Graph:
- The UI highlights referenced entities as clickable tags.
- An **"Explore in 3D Graph"** button links directly to:
  ```
  /?highlight=abhijeet-dipke,cjp,delhi-police
  ```
- Opening this link opens the 3D visualization, focuses the camera on the cluster of referenced entities, displays a highlight banner, and dims unrelated background entities.

---

## API Reference

### Graph Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/graph` | Retrieve nodes and links for 3D visualization. Supports `?limit=500`. |
| `GET` | `/api/graph/subgraph` | Multi-hop neighborhood traversal. Query: `?nodes=id1,id2&hops=2`. |
| `GET` | `/api/entities/{id}` | Entity metadata, aliases, and connected relationships. |
| `GET` | `/api/entities/search` | Full-text search across entities and aliases. Query: `?q=query`. |
| `GET` | `/api/events/{id}` | Event details, timestamps, location, and participants. |

### Query & Chat Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/query` | Execute graph-grounded question answering with optional live research. |
| `GET` | `/api/conversations` | List conversation sessions. Supports `?limit=50`. |
| `POST` | `/api/conversations` | Create a new conversation session. |
| `GET` | `/api/conversations/{id}` | Fetch conversation session details with full chronological message history. |

### Ingestion & System Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | System health check, database integrity, and entity/relationship counts. |
| `POST` | `/api/ingest` | Trigger manual news ingestion. Requires `X-API-Key: ADMIN_API_KEY`. |
| `GET` | `/api/ingest/status` | List historical background and manual ingestion job runs. |

---

## Database Backup & Maintenance

All persistent knowledge resides in `data/driftforge.db`.

### Online Database Backup
Because SQLite operates in `WAL` mode, you can safely create hot backups while the application server is running:

```bash
# SQLite online backup command:
sqlite3 data/driftforge.db ".backup data/driftforge_backup_$(date +%Y%m%d).db"
```

### Database Restoration
To restore from a backup file:
```bash
cp data/driftforge_backup_20261012.db data/driftforge.db
```
The server will pick up the restored database on next start without schema migration issues.

---

## License
MIT License. Built by [Import-Saurabh](https://github.com/Import-Saurabh).
