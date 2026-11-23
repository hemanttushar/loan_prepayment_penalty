"""Build ragkit pipelines for this solution: config per chunking strategy, vector store backend, and mode."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from ragkit.config import RAGConfig, config_from_dict
from ragkit.pipeline import RAGPipeline
from ragkit.vectorstore.base import VectorStore, make_vectorstore

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "base.toml"

# All six built-in chunking strategies in ragkit.chunking.strategies.
STRATEGIES = ["fixed", "recursive", "semantic", "markdown", "sentence_window", "parent_child"]
MODES = ("offline", "live")

# Vector store backends this solution can run on. Chosen with --backend, or VECTOR_BACKEND.
BACKENDS = ("weaviate", "pgvector")
DEFAULT_BACKEND = os.environ.get("VECTOR_BACKEND", "weaviate")


def load_config(strategy: str, backend: str = DEFAULT_BACKEND) -> RAGConfig:
    """Read config/base.toml and set the chunking strategy, the backend and a per-strategy collection."""
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy!r}. Choose one of {STRATEGIES}.")
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}. Choose one of {BACKENDS}.")
    with open(CONFIG_FILE, "rb") as fh:
        raw = tomllib.load(fh)
    raw["chunking"]["strategy"] = strategy

    # base.toml has one section per backend under [vectorstore]. Take the chosen one and drop the rest.
    vs = raw["vectorstore"]
    sections = {name: dict(vs.pop(name, {})) for name in BACKENDS}
    options = sections[backend]
    vs["backend"] = backend
    vs["options"] = options

    if backend == "weaviate":
        # In Docker, Weaviate runs as the "weaviate" service, so the URL comes from the environment.
        if os.environ.get("WEAVIATE_URL"):
            options["url"] = os.environ["WEAVIATE_URL"]
        # Weaviate class names keep letters and digits only, so underscores are removed here.
        vs["collection"] = f"loanpenalty{strategy.replace('_', '')}"
    else:
        # Postgres table names: lower-case letters, digits and underscores.
        vs["collection"] = f"loanpenalty_{strategy}"
    return config_from_dict(raw)


def vector_store(config: RAGConfig, reset: bool = False) -> VectorStore:
    """Connect to the configured backend. With reset=True, delete this strategy's collection first.

    Re-ingesting into an existing collection would keep chunks from earlier runs, because chunk ids
    can change between runs. A clean collection keeps each run's numbers honest.
    """
    store = make_vectorstore(config.vectorstore)
    if not reset:
        return store
    if config.vectorstore.backend == "weaviate":
        client, name = store._client, store._name  # WeaviateVectorStore internals
        if client.collections.exists(name):
            client.collections.delete(name)
        store._collection = None  # next add() recreates the collection
    elif config.vectorstore.backend == "pgvector":
        store._conn.execute(f"DROP TABLE IF EXISTS {store._qualified}")  # PgVectorStore internals
        store._ready = False  # next add() recreates the table
        store._dim = None
    return store


def build_pipeline(
    strategy: str,
    mode: str = "offline",
    reset: bool = False,
    store: VectorStore | None = None,
    backend: str = DEFAULT_BACKEND,
) -> RAGPipeline:
    """Return a pipeline for one chunking strategy and one vector store backend.

    - offline: ragkit's HashEmbedder and the scripted OfflineLLM. No API key needed.
    - live: OpenAI models from config/base.toml. Needs OPENAI_API_KEY.

    Pass ``store`` to use another store (for example an in-memory one in tests).
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    config = load_config(strategy, backend)
    store = store or vector_store(config, reset=reset)
    if mode == "live":
        return RAGPipeline(config, store=store)

    from ragkit.testing import HashEmbedder

    from prepayment.offline import OfflineLLM

    return RAGPipeline(config, llm=OfflineLLM(), embedder=HashEmbedder(), store=store)
