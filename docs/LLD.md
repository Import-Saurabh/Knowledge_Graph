# DriftForge — Low-Level Design (LLD) Document
**Detailed Component, Function, Class & Data Flow Specifications**
*Version: 2.0.0 | Date: October 2026 | Document Status: Approved*

---

## 1. Introduction & Scope

This document provides the Low-Level Design (LLD) for the **DriftForge News Intelligence Platform**. It is the implementation-level counterpart to the High-Level Design (HLD). It details:
- **System-Wide & Intra-Component Data Flow Diagrams** covering the complete lifecycle of news ingestion, entity resolution, graph retrieval, query-triggered research, and response synthesis.
- **Exhaustive Module Catalog** detailing every module in the project codebase.
- **Detailed Function & Method Specifications** including exact parameter signatures, return types, step-by-step algorithmic logic, error handling, database operations, and external API calls.

---

## 2. System Data Flow Diagrams

### 2.1 Autonomous Background Ingestion Flow
This flow is executed periodically (hourly) by `server.scheduler` or triggered manually via `POST /api/ingest`.

```mermaid
sequenceDiagram
    autonumber
    participant Sch as APScheduler / Admin API
    participant Pipe as IngestionPipeline (pipeline.py)
    participant RSS as RSSConnector (sources.py)
    participant DB as SQLite Store (database.py)
    participant LLM as LLMExtractor (extractor.py)
    participant Res as EntityResolver (resolver.py)
    participant Wri as GraphWriter (writer.py)
    participant Snap as graph.json Snapshot

    Sch->>Pipe: run(trigger="scheduler", force=False)
    Pipe->>DB: record_job(IngestionJob: status="running")
    
    Pipe->>RSS: discover_articles(max_per_feed=4)
    par Concurrent Feed Fetching (ThreadPoolExecutor)
        RSS->>RSS: Fetch BBC, NPR, Guardian, Al Jazeera, DW, France24
        RSS->>RSS: normalize_url(raw_link) -> Strip UTM/tracking
        RSS->>RSS: compute_sha256(clean_url) & compute_sha256(content)
    end
    RSS-->>Pipe: Return list[Article]
    
    loop For each discovered Article
        Pipe->>DB: article_exists_by_url(article.url)
        alt Article Exists
            Pipe->>Pipe: Increment job.articles_skipped
        else Article is New
            Pipe->>Pipe: Append to new_articles
        end
    end

    alt new_articles is Empty
        Pipe->>DB: record_job(status="completed", articles_processed=0)
        Pipe-->>Sch: Return completed job
    else new_articles has items
        Pipe->>LLM: extract(new_articles)
        LLM->>LLM: Format articles batch text with numbered indices
        LLM->>LLM: Call Claude/MiniMax Messages API (max_tokens=8192)
        LLM->>LLM: Sanitize and parse JSON response
        LLM-->>Pipe: Return dict(entities, events, relationships, claims)
        
        Pipe->>Wri: persist_extraction(new_articles, extracted_data)
        
        %% Step 1: Articles
        Wri->>DB: Upsert new_articles into articles table
        
        %% Step 2: Entities & Resolution
        loop For each raw entity
            Wri->>Res: resolve_entity_id(raw_id, raw_label)
            Res->>Res: slugify(raw_id or raw_label)
            Res->>DB: get_entity(slug) / search_entities(raw_label)
            Res-->>Wri: resolved_entity_id
            Wri->>DB: Upsert into entities table & sync entities_fts
        end
        
        %% Step 3: Events
        loop For each raw event
            Wri->>DB: Upsert into events table & sync events_fts
        end
        
        %% Step 4: Relationships
        loop For each raw relationship
            Wri->>Wri: Remap source & target to resolved_ids
            Wri->>DB: Upsert into relationships table ON CONFLICT UPDATE
        end
        
        %% Step 5: Claims
        loop For each raw claim
            Wri->>Wri: Remap subject & object to resolved_ids
            Wri->>DB: Insert into claims table (Foreign Keys to article & event)
        end
        
        %% Step 6: Snapshot
        Wri->>DB: get_all_graph_data(limit_nodes=500)
        Wri->>Snap: Dump JSON payload to graph.json
        Wri-->>Pipe: Return stats dict
        
        Pipe->>DB: record_job(status="completed", updated metrics)
        Pipe-->>Sch: Return completed job
    end
```

---

### 2.2 Conversational Graph RAG Query Flow
This flow processes user inquiries submitted via `POST /api/query` from the Graph Chat workspace (`chat.html`).

```mermaid
sequenceDiagram
    autonumber
    participant User as Web Browser (chat.html)
    participant Route as Query Router (routes/query.py)
    participant Engine as QueryEngine (engine.py)
    participant DB as SQLite Store (database.py)
    participant Retr as GraphRetriever (retriever.py)
    participant Resr as QueryResearcher (researcher.py)
    participant Synth as AnswerSynthesizer (synthesizer.py)
    participant LLM as Claude / MiniMax LLM

    User->>Route: POST /api/query { question, conversation_id, force_research }
    Route->>Engine: answer_question(QueryRequest)
    
    %% Session Management
    Engine->>DB: get_conversation(conv_id)
    alt Conversation Not Found
        Engine->>DB: create_conversation(conv_id, title=question[:50])
    end
    Engine->>DB: save_message(user_msg)
    
    %% Entity Recognition
    Engine->>Retr: identify_entities_in_text(question)
    Retr->>Retr: Generate 3-gram, 2-gram, 1-gram candidate phrases
    loop For candidate phrases (capped at 15)
        Retr->>DB: search_entities(phrase) via FTS5 MATCH / LIKE
    end
    Retr-->>Engine: matched_entities
    
    %% Research Assessment
    Engine->>Resr: should_trigger_research(question, matched_entities, force)
    alt force == True OR matched_entities is Empty
        Resr-->>Engine: should_research=True, reason="..."
        Engine->>Resr: perform_research(question, matched_entities)
        Note over Resr: Executes on-demand wire search & extraction (See Flow 2.3)
        Resr-->>Engine: research_meta dict with new articles & stats
        Engine->>Retr: Re-run identify_entities_in_text(question)
    else matched_entities Found & force == False
        Resr-->>Engine: should_research=False, reason="Existing graph context available"
    end
    
    %% Context Retrieval
    Engine->>Retr: get_multi_hop_context(entity_ids, max_hops=2)
    Retr->>DB: Recursive CTE query on relationships table
    Retr-->>Engine: subgraph {nodes, links}
    
    Engine->>Retr: get_events_for_entities(entity_ids, limit=8)
    Retr->>DB: Query events & entity_event_links
    Retr-->>Engine: events list
    
    Engine->>Retr: get_claims_and_evidence(entity_ids, limit=12)
    Retr->>DB: Query claims JOIN articles
    Retr-->>Engine: claims list
    
    Engine->>Retr: get_recent_articles_for_entities(entity_ids, limit=8)
    Retr->>DB: Query articles via claims & relationships lineage
    Retr-->>Engine: articles list
    
    %% Synthesis
    Engine->>Synth: synthesize(question, entities, subgraph, events, claims, articles, history)
    Synth->>Synth: Format context sections (Entities, Graph Links, Events, Claims, Articles)
    Synth->>LLM: Call Claude/MiniMax Messages API with SYNTHESIS_SYSTEM_PROMPT
    LLM-->>Synth: Raw LLM response containing markdown & ```explore_graph``` block
    Synth->>Synth: Parse explore_graph JSON block -> (entity_ids, event_ids)
    Synth->>Synth: Strip explore_graph from text -> clean_answer
    Synth->>Synth: Build Citation objects from referenced articles
    Synth-->>Engine: (clean_answer, citations, ref_entity_ids, ref_event_ids)
    
    %% Save & Respond
    Engine->>DB: save_message(assistant_msg)
    Engine-->>Route: QueryResponse
    Route-->>User: 200 OK QueryResponse JSON
```

---

### 2.3 Query-Triggered On-Demand News Research Flow
When a user asks about an emerging topic absent from the graph or explicitly clicks "Force Live Research", this flow executes synchronously within the query lifecycle.

```mermaid
flowchart TD
    Start["User Query with No Graph Match OR force_research=True"] --> ExtractNouns["Extract Capitalized Proper Nouns\nfrom question text"]
    Start --> CleanTopic["Strip conversational filler\n('what are', 'latest updates on')"]
    ExtractNouns --> Formulate["Formulate Targeted Search Queries\n(max 2 distinct queries)"]
    CleanTopic --> Formulate

    Formulate --> GNews["RSSConnector.search_topic_articles()\nQuery Google News RSS: https://news.google.com/rss/search?q={query}"]
    
    GNews --> Parse["Parse RSS XML entries\nExtract Headline, Link, Publisher, PubDate"]
    Parse --> Norm["Normalize URLs (strip tracking query params)\nCompute URL SHA-256 and Content SHA-256"]
    
    Norm --> CheckFallback{"Any Articles\nFound via Topic?"}
    CheckFallback -- No --> HarvestGeneral["Fallback: RSSConnector.discover_articles(max_per_feed=2)\nfrom BBC, NPR, Guardian, etc."]
    CheckFallback -- Yes --> Dedup["Deduplicate URLs in Memory"]
    HarvestGeneral --> Dedup

    Dedup --> FilterExisting["Filter against SQLite articles table\nvia GraphStore.article_exists_by_url(url)"]
    FilterExisting --> Cap["Select Top 3 New Candidate Articles"]
    
    Cap --> HasNew{"New Articles\nAvailable?"}
    HasNew -- Yes --> LLMEx["LLMExtractor.extract(new_articles)\nExtract Entities, Events, Links, Claims"]
    LLMEx --> Write["GraphWriter.persist_extraction()\nTransactional SQLite Commit & graph.json Update"]
    Write --> RetMeta["Assemble research_metadata payload\n(articles, counts, reporting period)"]
    HasNew -- No --> RetMeta
    
    RetMeta --> Resume["Resume Master Query Engine Retrieval"]
```

---

### 2.4 3D Force Graph Visualizer & Deep Link Navigation Flow
Illustrates how the frontend visualizer initializes and responds to highlight deep links generated by the chat workspace.

```mermaid
sequenceDiagram
    autonumber
    participant User as Browser
    participant Page as index.html (Three.js ForceGraph3D)
    participant API as FastAPI Backend (/api/graph)
    participant Chat as chat.html

    User->>Page: Navigate to https://driftforge.cloud/?highlight=saudi-arabia,houthi-movement
    Page->>API: GET /api/graph?limit=500
    API-->>Page: Return GraphResponse { nodes, links, generated_at, entity_count }
    
    Page->>Page: Parse URL search parameters (?highlight=id1,id2)
    Page->>Page: Compute node degrees & apply quadratic radius: val = max(4, deg^2 + 4)
    Page->>Page: Run Label Propagation algorithm for community coloring
    Page->>Page: Mount WebGL canvas & initialize 3D Force Graph simulation
    
    alt Highlight IDs Present in URL
        Page->>Page: Extract target IDs = ['saudi-arabia', 'houthi-movement']
        Page->>Page: Identify 1-hop neighbor nodes connected via links
        Page->>Page: Apply dimming: set opacity = 0.08 on non-target nodes and links
        Page->>Page: Highlight target nodes: set bright glow & increased scale
        Page->>Page: Compute 3D bounding sphere around target nodes
        Page->>Page: Programmatically animate Three.js camera (tween to focus coordinates)
        Page->>Page: Populate Side Drawer with entity details and relationship table
    end

    User->>Chat: User asks question in Graph Chat