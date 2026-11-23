# Architecture: loan prepayment penalty solution

Written for: engineers new to this repo.

This solution answers questions about early repayment penalties from three synthetic loan documents. It is built on [ragkit](../ragkit). ragkit does the parsing, chunking, embedding, vector storage, retrieval, answering and evaluation. This folder adds the data, the configuration, the command line, the Docker setup, and the wiring that runs six chunking strategies side by side on either of two vector databases.

## 1. Components

```mermaid
flowchart LR
    subgraph Inputs
        DATA["data/<br/>3 loan documents"]
        QS["evals/questions.jsonl<br/>11 questions"]
        CFG["config/base.toml<br/>shared and per-backend settings"]
        ENV[".env and environment<br/>OPENROUTER_API_KEY (live only)<br/>VECTOR_BACKEND, WEAVIATE_URL,<br/>PGVECTOR_DSN"]
    end

    subgraph Solution["prepayment/ (this solution)"]
        CLI["run.py<br/>command line, --backend"]
        SET["settings.py<br/>load_config(), build_pipeline()"]
        SOL["solution.py<br/>ingest_all, ask,<br/>evaluate_strategy, compare"]
        OFF["offline.py<br/>OfflineLLM"]
    end

    subgraph Ragkit["ragkit (shared library)"]
        RP["RAGPipeline"]
        PARSE["parsing"]
        CHUNK["chunking<br/>6 strategies"]
        EMB["embeddings"]
        RET["retrieval"]
        GEN["generation"]
        EVAL["evals<br/>8 metrics + judge"]
        MVS["make_vectorstore()<br/>picks the backend class"]
    end

    subgraph Stores["Vector databases (one runs at a time)"]
        WV[("Weaviate<br/>container weaviate<br/>host localhost:8085")]
        PG[("PostgreSQL + pgvector<br/>container postgres<br/>host localhost:5433")]
    end

    OR["OpenRouter API<br/>(live mode only)"]
    OUT["results/<br/>comparison_backend_mode.md/json<br/>per-strategy reports"]
    WRAP["run.sh / run.ps1<br/>start the chosen database,<br/>then run the app"]

    WRAP --> CLI
    CLI --> SET
    CLI --> SOL
    SOL --> SET
    SET --> CFG
    SET --> ENV
    SET --> RP
    SET -. offline mode .-> OFF
    SOL --> DATA
    SOL --> QS
    RP --> PARSE --> CHUNK --> EMB
    RP --> RET --> MVS
    MVS -. backend = weaviate .-> WV
    MVS -. backend = pgvector .-> PG
    RP --> GEN
    RP --> EVAL
    RP --> MVS
    EMB -. live .-> OR
    GEN -. live .-> OR
    EVAL -. live .-> OR
    SOL --> OUT
```

| Path | Role |
|---|---|
| `run.py` | Command line. Subcommands: `ingest`, `ask`, `evaluate`, `compare`. `--backend weaviate\|pgvector` works before or after the subcommand. |
| `run.sh`, `run.ps1` | Wrappers. They start the database for the chosen backend (its compose profile), wait until it is ready, then run `run.py` in the `app` container. |
| `prepayment/settings.py` | Loads `config/base.toml`, takes the chosen backend's section, sets the collection name, and builds a `RAGPipeline`. `vector_store()` deletes the old collection when a run starts clean. |
| `prepayment/solution.py` | The use case: ingest the three documents with metadata, answer a question, evaluate one strategy, compare all strategies. |
| `prepayment/offline.py` | A deterministic stand-in for the LLM (word-overlap heuristics). Used when there is no API key. |
| `config/base.toml` | Shared settings: model, embedding, chunking defaults, retrieval, eval metrics and thresholds. Plus `[vectorstore.weaviate]` (URL, gRPC port) and `[vectorstore.pgvector]` (name of the environment variable that holds the connection string). |
| `data/` | The three documents. Each has metadata set in `DOCUMENTS` in `solution.py`. |
| `evals/questions.jsonl` | Evaluation questions with reference answers. |
| `tests/test_solution.py` | Tests for coverage, loan-type filtering, refusal of out-of-scope questions, backend config, the pgvector pipeline, and metrics. |
| `docker-compose.yml` | Services `weaviate` (profile `weaviate`), `postgres` (profile `pgvector`), and `app`. |
| `Dockerfile` | Builds the `app` image from Python 3.12, ragkit with its Weaviate and pgvector extras, and this solution. |

## 2. Modes

The same code runs in two modes, chosen with `--mode`.

| | `offline` (default) | `live` |
|---|---|---|
| Embeddings | ragkit `HashEmbedder` (no network) | `openai_compatible` via OpenRouter, `openai/text-embedding-3-small` |
| Answers and judges | `OfflineLLM` (heuristics) | OpenRouter, `openai/gpt-5.6-luna` |
| Needs `OPENROUTER_API_KEY` | No | Yes |
| Use it for | Checking wiring, comparing chunking strategies quickly | Real evaluation numbers |

`OfflineLLM` is not a measure of answer quality. Its scores only show that the pipeline is wired correctly. The mode and the backend are independent: any backend works in either mode.

## 3. Vector store backends

The backend is chosen by `--backend` (or the `VECTOR_BACKEND` environment variable, default `weaviate`). The solution supports two:

| | Weaviate | PostgreSQL + pgvector |
|---|---|---|
| Compose service and profile | `weaviate` / `weaviate` | `postgres` / `pgvector` |
| Host port | 8085 (HTTP), 50051 (gRPC) | 5433 (inside the container: 5432) |
| Collection name | `Loanpenalty<strategy>`, underscores removed (for example `Loanpenaltyrecursive`) | table `loanpenalty_<strategy>` (for example `loanpenalty_recursive`) |
| Connection | `WEAVIATE_URL=http://weaviate:8080` inside Docker | `PGVECTOR_DSN=postgresql://ragkit:ragkit@postgres:5432/ragkit` inside Docker |
| Inspect with | HTTP API (`/v1/schema`) | SQL in DBeaver or psql |
| Filters | Weaviate property filters | `metadata @> '{...}'` (jsonb containment) |

Both implement ragkit's `VectorStore` protocol (`add`, `search`, `get`, `count`). `make_vectorstore()` in ragkit creates the right one, and only that backend's client library is imported. The solution code never mentions a backend class directly.

Only one backend is started per run. Each one lives in its own compose profile, and the wrapper starts only the one you ask for.

## 4. Chunking strategies

`compare` runs these six strategies, and each one gets its own collection on the chosen backend (see section 3 for the names).

`fixed`, `recursive`, `semantic`, `markdown`, `sentence_window`, `parent_child`

Chunk size, overlap, and the parent and child sizes come from `config/base.toml`. `retrieval.expand_to_parent = true` means that `sentence_window` and `parent_child` return the parent passage for a matching child.

## 5. Ingest flow

`ingest_all` runs once per document. `build_pipeline(..., reset=True)` deletes the strategy's collection first, so each run starts clean. Chunk IDs can change between runs, so leftover chunks would skew the metrics.

```mermaid
sequenceDiagram
    autonumber
    participant CLI as run.py
    participant S as solution.ingest_all
    participant P as RAGPipeline
    participant R as ragkit parsing + chunking
    participant E as Embedder
    participant VS as Vector store (Weaviate or pgvector)

    CLI->>P: build_pipeline(strategy, mode, reset=True, backend)
    P->>VS: drop the strategy's collection or table if it exists
    loop each of 3 documents in DOCUMENTS
        S->>P: ingest([file], metadata: loan_type, document)
        P->>R: parse_file(file)
        R-->>P: text
        P->>R: chunk_document_with_report(strategy)
        R-->>P: chunks + coverage report
        opt contextualize enabled and LLM present
            P->>P: add_context(chunks)
        end
        opt index_questions enabled
            P->>P: hypothetical questions per chunk
        end
        P->>E: embed_documents(chunk texts)
        E-->>P: vectors
        P->>VS: add(chunks, vectors), upsert by chunk id
    end
    S-->>CLI: IngestReport list (chunk counts)
```

Every chunk stores `loan_type` and `document` as metadata. That metadata is what lets `ask --loan-type` filter results. On pgvector it is stored as jsonb, so numbers keep their type.

## 6. Question answering flow

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant CLI as run.py ask
    participant P as RAGPipeline
    participant RT as Retriever
    participant VS as Vector store (Weaviate or pgvector)
    participant G as generate_answer
    participant L as LLM

    U->>CLI: question [--loan-type] [--backend]
    CLI->>P: ingest_all (unless --no-ingest)
    CLI->>P: query(question, where={loan_type})
    P->>RT: retrieve(question, where)
    RT->>VS: vector search, candidate_k = 12
    VS-->>RT: candidates with metadata
    RT->>RT: keep top_k = 4, expand to parent if configured
    RT-->>P: hits
    P->>G: generate_answer(llm, question, hits)
    G->>L: prompt with the passages
    L-->>G: answer text
    G-->>P: Answer (answer + contexts)
    P-->>CLI: answer
    CLI-->>U: answer, then [n] document | section (score)
```

If the documents do not cover the question, the model is instructed to refuse. `tests/test_solution.py` checks this with an out-of-scope question.

## 7. Evaluation and comparison flow

`evaluate_strategy` answers every question in `evals/questions.jsonl` through the same query path as `ask`. It then scores the results with the eight metrics from `config/base.toml`: faithfulness, answer relevance (LLM and semantic versions), context relevance, groundedness, context precision, context recall, and noncommittal.

```mermaid
flowchart TD
    START(["run.sh --backend X compare --mode Y"]) --> DB["start the database for X<br/>(compose profile, waits until ready)"]
    DB --> LOOP{{"for each of 6 strategies"}}
    LOOP --> BP["build_pipeline(strategy, mode, reset=True, backend=X)"]
    BP --> ING["ingest_all: 3 documents"]
    ING --> LOAD["load evals/questions.jsonl<br/>(11 questions)"]
    LOAD --> Q["for each question:<br/>query() gives answer + contexts"]
    Q --> M["score 8 metrics<br/>judge LLM and embedder"]
    M --> REP["write results/X_Y_strategy/<br/>per-question report"]
    REP --> SUM["summary, coverage, chunk count"]
    SUM --> LOOP
    LOOP -- done --> TAB["comparison_X_Y.json<br/>comparison_X_Y.md table"]
    TAB --> END(["printed to terminal"])
```

`run.py evaluate --strategy S` runs the same steps for one strategy. It exits with code 1 when a metric falls below its threshold in `[evals.thresholds]`. The thresholds are `faithfulness = 0.7` and `context_recall = 0.6`.

## 8. Docker and configuration

- Start a database with its profile: `docker compose --profile weaviate up -d --wait weaviate`, or `docker compose --profile pgvector up -d --wait postgres`. The wrapper does this for you.
- The `app` service has no `depends_on`, because the wrapper starts the right database. Running `docker compose run app` directly needs the database started first.
- Settings are layered. `config/base.toml` holds shared defaults. `load_config(strategy, backend)` picks the backend's section, drops the other one, and sets the collection name. Environment variables supply the Weaviate URL, the Postgres connection string, and the backend itself.
- Secrets are read from the environment only. `OPENROUTER_API_KEY` is never written to a file or a result. The Postgres password is the local development value `ragkit`, set in `docker-compose.yml`. Change it there if you expose the database.
- Port 5433 is used on the host for Postgres so it does not clash with another PostgreSQL server on 5432.

## 9. Output

| File | Contents |
|---|---|
| `results/comparison_<backend>_<mode>.md` | Table with one row per strategy: chunk count, coverage, and each metric score. |
| `results/comparison_<backend>_<mode>.json` | The same data as JSON, with a `backend` field per row. |
| `results/<backend>_<mode>_<strategy>/` | Per-question detail for one strategy, written by ragkit's `EvalReport.write`. |

Results from before the backend was added to the names are still in `results/` as `comparison_<mode>.*` and `<mode>_<strategy>/`. They are not regenerated.

## 10. Where to start reading

1. `run.py`: the commands, the `--backend` flag, and what each one calls.
2. `run.sh` or `run.ps1`: how the chosen database is started before the app runs.
3. `prepayment/solution.py`: the use case in about 80 lines.
4. `prepayment/settings.py`: how one strategy and one backend become a pipeline.
5. `config/base.toml`: every tunable value in one file, including the per-backend sections.
6. In ragkit: `src/ragkit/pipeline.py` (`RAGPipeline.ingest`, `query`, `evaluate`), `src/ragkit/vectorstore/` (one folder per backend, including `pgvector/`), and `src/ragkit/chunking/`.
