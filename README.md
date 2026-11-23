# Loan prepayment penalty: run it on your laptop with Docker

This solution answers questions about early repayment penalties from synthetic loan documents. It indexes the documents into a vector database with six chunking strategies, and scores the answers with all eight ragkit metrics. You pick the database with a flag: **Weaviate** or **PostgreSQL with pgvector**. Everything runs in Docker, so you don't need Python or either database installed.

*All bank names, documents and figures are fictional.*

Commands are shown for both **Windows PowerShell** and **macOS / Linux / Git Bash**. Where only one is shown, the other is the same.

---

## 1. What you need

- **Docker Desktop** (Windows or macOS) or Docker Engine (Linux), with Docker Compose v2.
- About 3 GB of free disk space for the images.
- An **OpenAI API key**, only if you want live mode. Offline mode needs no key.
- On Windows, **Windows PowerShell** (built into Windows) is enough. Git Bash is optional.

Check Docker is working (same in every shell):

```bash
docker --version
docker compose version
docker info          # should print server details, not an error
```

If `docker info` shows an error, start Docker Desktop and wait until its status says "running".

## 2. Get the project

Keep the `atlas` folder layout as it is. The Docker build reads two folders next to each other:

```
atlas/
├── ragkit/                     the RAG library (must stay here)
└── loan_prepayment_penalty/    this solution
```

Open a terminal in the `loan_prepayment_penalty` folder for the steps below. In Windows Explorer, open the folder, click the address bar, type `powershell`, and press Enter.

## 3. Start a vector database

Choose one. Each database runs in its own Docker container, and the compose profile starts only that one.

### Option A: Weaviate

Start it and wait until it is ready (same in every shell):

```bash
docker compose --profile weaviate up -d --wait weaviate
```

Check it responds with HTTP 200.

macOS / Linux / Git Bash:

```bash
curl http://localhost:8085/v1/.well-known/ready
```

Windows PowerShell:

```powershell
curl.exe http://localhost:8085/v1/.well-known/ready
```

In PowerShell, `curl` on its own runs a different command, so use `curl.exe`. You can also open the URL in a browser.

| | |
|---|---|
| Container | `weaviate` (image `weaviate:1.30.5`) |
| Host ports | `8085` (HTTP), `50051` (gRPC) |
| Data volume | `weaviate_data` |
| Look at the data | HTTP API, see section 6 |

### Option B: PostgreSQL with pgvector

Start it and wait until it is ready (same in every shell):

```bash
docker compose --profile pgvector up -d --wait postgres
```

Check it accepts connections (same in every shell):

```bash
docker compose exec postgres pg_isready -U ragkit -d ragkit
```

| | |
|---|---|
| Container | `postgres` (image `pgvector/pgvector:pg17`) |
| Host port | `5433` (inside the container it is 5432) |
| Database, user, password | `ragkit`, `ragkit`, `ragkit` |
| Data volume | `postgres_data` |
| Look at the data | DBeaver or any PostgreSQL client, see section 6 |

### Option C: let the wrapper start it

The wrapper starts the database for the flag you pass, then runs your command on it. You don't need the commands above.

macOS / Linux / Git Bash:

```bash
./run.sh --backend weaviate compare      # starts Weaviate, then runs the comparison
./run.sh --backend pgvector compare      # starts PostgreSQL, then runs the comparison
```

Windows PowerShell:

```powershell
.\run.ps1 --backend weaviate compare     # starts Weaviate, then runs the comparison
.\run.ps1 --backend pgvector compare     # starts PostgreSQL, then runs the comparison
```

If you leave out `--backend`, Weaviate is used.

If PowerShell says scripts are disabled, allow local scripts for your user once, then try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### If a port is taken

If something on your machine already uses port 8085, 50051 or 5433, stop it, or change the left-hand port in `docker-compose.yml`.

## 4. Build the solution image

Same in every shell:

```bash
docker compose build app
```

The first build takes a few minutes. It installs ragkit with its PDF, OpenAI, Weaviate and pgvector extras into a Python 3.12 image. Later runs with the wrapper rebuild only if the code changed.

## 5. Run it

### Offline mode (no API key)

This is the default. It indexes all six chunking strategies into the chosen database, runs all eight metrics on the 11 questions, and writes the results.

macOS / Linux / Git Bash:

```bash
./run.sh --backend weaviate compare      # or: ./run.sh --backend pgvector compare
```

Windows PowerShell:

```powershell
.\run.ps1 --backend weaviate compare     # or: .\run.ps1 --backend pgvector compare
```

When it finishes, the results appear on your laptop:

- `results/comparison_<backend>_offline.md`: one row per chunking strategy, with every metric
- `results/comparison_<backend>_offline.json`: the same numbers in JSON
- `results/<backend>_offline_<strategy>/`: per-question details (`report.json`, `per_sample.csv`)

`<backend>` is `weaviate` or `pgvector`, so runs on different databases don't overwrite each other.

> Offline scores check that the pipeline works and let you compare strategies. They are not measures of answer quality. See section 8.

The examples below use `pgvector`. Replace it with `weaviate` to use Weaviate.

### Run the tests

The tests include a pgvector check, so start Postgres first. The commands are the same in every shell:

```bash
docker compose --profile pgvector up -d --wait postgres
docker compose run --rm app python -m pytest tests -q
```

Expected output: `22 passed`.

### Live mode (real OpenAI models)

1. Copy the example file and add your key.

   macOS / Linux / Git Bash:

   ```bash
   cp .env.example .env
   ```

   Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

   Open `.env` in a text editor and replace `sk-your-key-here` with your key.

2. Run.

   macOS / Linux / Git Bash:

   ```bash
   ./run.sh --backend pgvector compare --mode live
   ```

   Windows PowerShell:

   ```powershell
   .\run.ps1 --backend pgvector compare --mode live
   ```

   This calls OpenAI for embeddings and for every judge check, so it costs money. Check the size of the run first: 6 strategies × 11 questions × several judge calls each.

Results are written to `results/comparison_<backend>_live.md` and `results/<backend>_live_<strategy>/`.

### Ask one question

macOS / Linux / Git Bash:

```bash
./run.sh --backend pgvector ingest --strategy markdown
./run.sh --backend pgvector ask "What is the penalty if a personal loan is repaid in month 20?" --strategy markdown --no-ingest
./run.sh --backend pgvector ask "What is the early repayment charge on a fixed-rate mortgage in year 2?" --strategy markdown --no-ingest --loan-type mortgage
```

Windows PowerShell:

```powershell
.\run.ps1 --backend pgvector ingest --strategy markdown
.\run.ps1 --backend pgvector ask "What is the penalty if a personal loan is repaid in month 20?" --strategy markdown --no-ingest
.\run.ps1 --backend pgvector ask "What is the early repayment charge on a fixed-rate mortgage in year 2?" --strategy markdown --no-ingest --loan-type mortgage
```

`ingest` replaces the collection for that strategy (a Weaviate class, or a Postgres table). The `--no-ingest` flag queries the existing one.

### Evaluate one strategy

macOS / Linux / Git Bash:

```bash
./run.sh --backend pgvector evaluate --strategy parent_child
```

Windows PowerShell:

```powershell
.\run.ps1 --backend pgvector evaluate --strategy parent_child
```

It exits with code 1 if any metric falls below its threshold in `config/base.toml`.

## 6. Look at the data

### Weaviate: HTTP API

macOS / Linux / Git Bash:

```bash
curl http://localhost:8085/v1/schema
```

Windows PowerShell:

```powershell
curl.exe http://localhost:8085/v1/schema
```

This lists one collection per strategy: `Loanpenaltyfixed`, `Loanpenaltyrecursive`, `Loanpenaltysemantic`, `Loanpenaltymarkdown`, `Loanpenaltysentencewindow`, `Loanpenaltyparentchild`.

### pgvector: SQL in DBeaver or psql

Each chunking strategy is one table: `loanpenalty_<strategy>` (for example `loanpenalty_markdown`). In DBeaver, create a PostgreSQL connection with host `localhost`, port `5433`, database `ragkit`, user `ragkit`, password `ragkit`. Then run, for example:

```sql
SELECT id, doc_id, left(text, 80) AS text, metadata FROM loanpenalty_markdown LIMIT 20;
SELECT id FROM loanpenalty_markdown WHERE metadata @> '{"loan_type": "mortgage"}';
```

The `embedding` column holds the vectors. The table is replaced each time you run `ingest` or `compare` for that strategy.

To run SQL from the terminal instead of DBeaver (same in every shell):

```bash
docker compose exec postgres psql -U ragkit -d ragkit -c "SELECT id, doc_id FROM loanpenalty_markdown LIMIT 5;"
```

## 7. Stop and clean up

Stop one database and keep its data (same in every shell):

```bash
docker compose --profile weaviate stop weaviate
docker compose --profile pgvector stop postgres
```

Stop everything this solution started, and keep the data:

```bash
docker compose --profile weaviate --profile pgvector down
```

Delete the data as well (Weaviate collections and Postgres tables are lost):

```bash
docker compose --profile weaviate --profile pgvector down -v
```

To start again, repeat section 3 or use the wrapper with the flag you want. The data stays unless you used `-v`.

## 8. What the offline numbers mean

Offline mode uses simple word-overlap rules instead of a language model. It checks parsing, chunking, storage, retrieval and every metric's code path. Two things follow:

- **Offline scores are not answer quality.** Use them to compare the pipeline and the chunking strategies.
- **Reference-free metrics can miss a wrong answer.** For example, the offline run answers "repaid in month 20 under the template" with the 2024 amendment's 1.5% instead of the template's 2%. `faithfulness` still scores it high, because the sentence exists in the documents. `context_recall` and the live judge are the checks that catch this.

Use live mode for real numbers. Both backends give the same offline numbers, so the choice of database does not change the scores.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Start Docker Desktop and wait until it says "running". |
| `port is already allocated` on 8085, 50051 or 5433 | Another program uses the port. Stop it, or change the left-hand port in `docker-compose.yml`. |
| `app` exits with `Cannot reach Weaviate` | Start Weaviate with `docker compose --profile weaviate up -d --wait weaviate`, or use the wrapper with `--backend weaviate`. |
| `app` exits with a connection error to `postgres` | Start Postgres with `docker compose --profile pgvector up -d --wait postgres`, or use the wrapper with `--backend pgvector`. |
| PowerShell: `curl` shows an error or a different output | Use `curl.exe`, not `curl`. |
| PowerShell: `running scripts is disabled on this system` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again. |
| PowerShell: `.\run.ps1` is not recognised | Make sure you are in the `loan_prepayment_penalty` folder (`cd` to it), and that the file is there with `dir run.ps1`. |
| Git Bash: `./run.sh: Permission denied` | Run it with `bash run.sh ...`. |
| Live mode says the key is missing (or 401 Unauthorized) | Check that `.env` has your key. Then run the wrapper with `--mode live`. |
| The build fails while installing packages | Check your internet connection, then run `docker compose build --no-cache app`. |
| Results folder is empty | Check the run finished without errors. Results are written into `results/` in this folder. |

## 10. Files in this folder

```
loan_prepayment_penalty/
├── Dockerfile                  builds the solution image (Python 3.12 + ragkit)
├── Dockerfile.dockerignore     keeps the build small: only ragkit/ and this folder
├── docker-compose.yml          weaviate and postgres services (profiles), and the app
├── run.sh                      wrapper for macOS, Linux and Git Bash
├── run.ps1                     wrapper for Windows PowerShell
├── .env.example                template for your OpenAI key (copy to .env)
├── data/                       synthetic loan documents (Markdown, text, HTML)
├── config/base.toml            ragkit settings, per-backend settings, thresholds
├── evals/questions.jsonl       11 questions with reference answers
├── prepayment/                 solution code (settings, solution, offline stand-in)
├── run.py                      command line
├── architecture.md             how the solution is built
├── tests/                      offline tests
└── results/                    created by runs (ignored by the build)
```
