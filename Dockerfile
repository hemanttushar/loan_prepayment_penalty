# Build context is the atlas folder (see docker-compose.yml), so both ragkit and this solution are available.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install ragkit from its source, with the extras this solution uses (both vector store clients).
COPY ragkit /opt/ragkit
RUN pip install --no-cache-dir "/opt/ragkit[openai,pdf,weaviate,pgvector]" pytest

# The solution itself.
WORKDIR /app
COPY loan_prepayment_penalty/ /app/

ENV WEAVIATE_URL=http://weaviate:8080 \
    PGVECTOR_DSN=postgresql://ragkit:ragkit@postgres:5432/ragkit \
    VECTOR_BACKEND=weaviate

# Default: index all six chunking strategies into Weaviate and write results/ (offline mode, no API key).
# Use run.sh or run.ps1 with --backend to pick pgvector instead.
CMD ["python", "run.py", "compare"]
