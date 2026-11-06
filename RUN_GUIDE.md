# DriftForge — Project Run & Execution Guide

This guide details all prerequisites, commands, and steps to configure, run, and test the DriftForge News Intelligence Platform both natively and via Docker.

---

## 📋 Prerequisites

| Requirement | Native | Docker |
|---|---|---|
| OS | Windows 10/11, macOS, Linux | Any OS with Docker support |
| Python | 3.10+ (3.11 recommended) | Bundled in Docker |
| RAM | 4 GB minimum (8 GB recommended) | 4 GB allocated |
| Internet | Access to RSS feeds and LLM API | Same |

---

## ⚙️ Native Setup (Step-by-Step)

### 1. Clone & Enter Project Directory

```bash
git clone https://github.com/Import-Saurabh/Knowledge_Graph.git
cd Knowledge_Graph
```

### 2. Create and Activate Virtual Environment

- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```

- **Windows (Command Prompt - CMD)**:
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate.bat
  ```

- **macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Required Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verify that critical native extensions (Kùzu, Newspaper4k, FastAPI) are installed properly:
```bash
python -c "import kuzu, newspaper, gnews, fastapi, anthropic; print('Dependencies OK')"
```

### 4. Configure Environment Variables

Copy the provided template and add your credentials:

- **Windows (PowerShell)**:
  ```powershell
  Copy-Item .env.example .env
  ```
- **macOS / Linux / Bash**:
  ```bash
  cp .env.example .env
  ```

Edit `.env` and set your API key:
```env
# LLM Settings (MiniMax Anthropic-compatible or Anthropic)
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
ANTHROPIC_API_KEY=your_minimax_or_anthropic_api_key_here
LLM_MODEL=MiniMax-M3
LLM_TIMEOUT=60

# Server Settings
HOST=0.0.0.0
PORT=8080
DATABASE_PATH=data/driftforge.db
TIMEZONE=UTC

# Security
ADMIN_API_KEY=driftforge-admin-secret

# Scheduling & Ingestion Limits
SCHEDULER_ENABLED=true
INGESTION_SCHEDULE_MINUTES=5
MAX_ARTICLES_PER_FEED=30
MAX_PROCESS_PER_RUN=50
GNEWS_MAX_PER_DOMAIN=10
```

---

## 🐳 Docker Setup (Smooth Execution on Any Machine)

DriftForge includes a production multi-stage `Dockerfile` and `docker-compose.yml` with persistent storage and healthchecks.

### 1. Build and Run Container

```bash
# Build the image and start the service in background
docker compose up --build -d
```

### 2. Check Container Logs & Health

```bash
# Follow logs
docker compose logs -f driftforge

# Inspect container health
docker ps --filter "name=driftforge-app"
```

### 3. Stop or Restart Container

```bash
# Stop containers
docker compose down

# Full reset (removes stored graph volume)
docker compose down -v
```

---

## 🚀 Running the Project Natively

### Standard Run (with Venv Activated)

- **Windows (PowerShell / CMD)**:
  ```powershell
  python -m uvicorn server.app:app --host 127.0.0.1 --port 8080
  ```

- **macOS / Linux**:
  ```bash
  python -m uvicorn server.app:app --host 127.0.0.1 --port 8080
  ```

### Development Mode (Auto-Reload on Code Change)

```bash
python -m uvicorn server.app:app --host 127.0.0.1 --port 8080 --reload
```

---

## 🌐 Application URLs

Once the server is running, access the following in your web browser:

| Interface / Service | URL | Description |
|---|---|---|
| **3D Knowledge Graph** | [http://127.0.0.1:8080](http://127.0.0.1:8080) | Interactive 3D WebGL knowledge graph visualizer |
| **Graph Chat** | [http://127.0.0.1:8080/chat](http://127.0.0.1:8080/chat) | Conversational Graph RAG with citations |
| **Swagger API Docs** | [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs) | Interactive API documentation & manual test UI |
| **Health Check API** | [http://127.0.0.1:8080/api/health](http://127.0.0.1:8080/api/health) | Live database, entity, and ingestion metrics |

---

## 🧪 Testing & Diagnostics

### Run the Full Test Suite

All 34 tests execute locally without live network calls:

```powershell
.venv\Scripts\pytest tests/ -v
```

### Verify Service Health via CLI

- **PowerShell**:
  ```powershell
  Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/health" -Method Get | ConvertTo-Json
  ```

- **cURL / Bash**:
  ```bash
  curl -s http://127.0.0.1:8080/api/health
  ```

### Trigger Manual News Ingestion

- **PowerShell**:
  ```powershell
  Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/ingest" -Method Post -Headers @{"X-API-Key"="driftforge-admin-secret"} -Body '{"force": false}' -ContentType "application/json"
  ```

- **cURL / Bash**:
  ```bash
  curl -X POST http://127.0.0.1:8080/api/ingest \
       -H "X-API-Key: driftforge-admin-secret" \
       -H "Content-Type: application/json" \
       -d '{"force": false}'
  ```

---

## 📌 Architectural & Performance Notes

1. **Dual Persistence Layer**:
   - Primary operational records are held in SQLite with WAL (Write-Ahead Logging) mode and FTS5 full-text indexing.
   - Graph topology and multi-hop Cypher queries run in embedded Kùzu.
2. **Paced Ingestion**:
   - Feeds are queried concurrently.
   - News articles are interleaved between standard RSS and GNews redirects.
   - Pacing limit (`MAX_PROCESS_PER_RUN=50`) prevents rate-limiting and timeouts.
3. **Resilient LLM Extraction**:
   - Supports thinking blocks (e.g. MiniMax-M3.1-Flash).
   - Robust parsing tolerates non-numeric article indices without dropping batches.
   - Articles that fail extraction are tracked as failed rather than being silently marked pending forever.
