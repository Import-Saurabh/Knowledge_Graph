# DriftForge — Persistent News Knowledge Graph & Graph Chat

A production-grade, persistent, continuously updated, evidence-backed news intelligence platform with an interactive **3D Knowledge Graph** visualization and a dedicated conversational **Graph Chat** workspace.



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
git clone https://github.com/Import-Saurabh/Knowledge_Graph.git
cd Knowledge_Graph

# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the template to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your settings:
```ini
HOST=0.0.0.0
PORT=8080
DATABASE_PATH=data/driftforge.db

# LLM Configuration (MiniMax Anthropic-compatible or native Anthropic)
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
ANTHROPIC_API_KEY=your_api_key_here
LLM_MODEL=MiniMax-M3

ADMIN_API_KEY=driftforge-admin-secret
SCHEDULER_ENABLED=true
INGESTION_SCHEDULE_HOURS=1
```

### 3. Run the Application
```bash
# Windows:
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload

# Linux/macOS:
uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
```

Open your browser at:
- **3D Knowledge Graph**: `http://localhost:8080/`
- **Graph Chat Workspace**: `http://localhost:8080/chat`
- **Interactive API Docs**: `http://localhost:8080/docs`

---

## API Reference

### Graph Endpoints
- `GET /api/graph` — Retrieve nodes and links for 3D visualization. Supports `?limit=500`.
- `GET /api/graph/subgraph?nodes=russia,ukraine&hops=2` — Multi-hop neighborhood traversal.
- `GET /api/entities/{id}` — Entity metadata and connected relationships.
- `GET /api/entities/search?q=saudi` — Full-text search across entities and aliases.
- `GET /api/events/{id}` — Event details and recorded timestamps.

### Query & Chat Endpoints
- `POST /api/query` — Execute graph-grounded question answering and research.
  ```json
  {
    "question": "What are today's major Saudi Arabia-Houthi developments?",
    "conversation_id": "optional-uuid",
    "force_research": false
  }
  ```
- `GET /api/conversations` — List conversation sessions.
- `POST /api/conversations` — Create a new conversation session.
- `GET /api/conversations/{id}` — Fetch conversation with complete message history.

### Ingestion & System Endpoints
- `GET /api/health` — System health, database connectivity, and entity counts.
- `POST /api/ingest` — Trigger manual news ingestion (Requires `X-API-Key: ADMIN_API_KEY`).
- `GET /api/ingest/status` — History of background and manual ingestion jobs.

---

## Production Deployment

### Docker Deployment
```bash
# Build and run with Docker Compose
docker compose up -d --build

# View container logs
docker compose logs -f driftforge
```

### Database Backup & Recovery
All persistent data resides in `data/driftforge.db`.
```bash
# Backup SQLite database safely using online backup API:
sqlite3 data/driftforge.db ".backup data/driftforge_backup_$(date +%Y%m%d).db"

# Restore database:
cp data/driftforge_backup_20261011.db data/driftforge.db
```

---

## Testing

Run the automated test suite:
```bash
.\.venv\Scripts\pytest.exe -v
```
The test suite validates:
- SQLite schema initialization, CRUD operations, and FTS5 search
- URL normalization, RSS feed parsing, and article deduplication
- Entity slugification and alias management
- FastAPI endpoint responses and authentication barriers
