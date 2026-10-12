# DriftForge — Persistent News Knowledge Graph & Graph Chat

A production-grade, persistent, continuously updated, evidence-backed news intelligence platform with an interactive **3D Knowledge Graph** visualization and a dedicated conversational **Graph Chat** workspace.

Live site: **https://driftforge.cloud**

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
│   │             (Runs hourly news updates autonomously)            │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│   External Services: MiniMax / Anthropic LLM API · RSS News Feeds      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Features

### 1. 3D Knowledge Graph Visualization (`/`)
- Interactive WebGL/Three.js force-directed 3D network (`index.html`).
- Quadratic node radius scaling based on connectivity degree.
- Real-time community detection via label propagation and sentiment link coloring.
- Dynamic entity search with automatic camera zoom-to-fit.
- **Graph Chat Integration**: Supports `?highlight=id1,id2` deep links from Graph Chat with focused camera framing, dimmed background nodes, and clear selection controls.

### 2. Graph Chat Workspace (`/chat`)
- Dedicated conversational intelligence workspace matching DriftForge dark aesthetics.
- Multi-turn conversation sessions with persistent history in SQLite.
- **Evidence-Grounded Synthesis**: LLM briefings cite specific graph nodes, relationships, and verified media articles.
- **Verified Sources & Evidence**: Direct citation links with publisher tags (BBC, NPR, Guardian, Al Jazeera, etc.).
- **Explore in 3D Graph**: One-click action navigating directly from a chat answer to the corresponding highlighted entities in the 3D visualization.
- **Query-Triggered Fresh News Research**: On-demand wire discovery for emerging topics or breaking events.

### 3. Persistent Knowledge Graph (SQLite + FTS5)
- ACID persistence in SQLite with Write-Ahead Logging (`WAL`) mode.
- Entity resolution with canonical slugs, aliases, and idempotent deduplication.
- Preserves historical knowledge across pipeline runs without resetting previous state.
- Full-text search on entities and events via SQLite FTS5.
- Auto-seeds from existing `graph.json` baseline upon first startup.

### 4. Continuous Ingestion Pipeline & Scheduler
- Automated RSS feed harvesting from world news sources.
- Per-source error isolation ensuring individual feed failures never break the pipeline.
- Autonomous background worker powered by APScheduler running hourly.
- Admin-protected manual ingestion endpoint (`POST /api/ingest`).

---

## Getting Started (Local Development)

### Prerequisites
- Python 3.10+
- Virtual environment (`.venv`)

### 1. Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/richardholliday/graph-app.git
cd graph-app

# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
