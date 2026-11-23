"""Offline tests: they use ragkit's in-memory store, so no Weaviate server or API key is needed."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from ragkit.evals.dataset import load_jsonl  # noqa: E402
from ragkit.evals.metrics import METRICS  # noqa: E402
from ragkit.vectorstore.memory import MemoryVectorStore  # noqa: E402

from prepayment.settings import STRATEGIES, build_pipeline, load_config  # noqa: E402
from prepayment.solution import QUESTIONS, ask, ingest_all  # noqa: E402

ALL_METRICS = [
    "faithfulness",
    "answer_relevance",
    "answer_relevance_semantic",
    "context_relevance",
    "groundedness",
    "context_precision",
    "context_recall",
    "noncommittal",
]


def _pipeline(strategy: str):
    return build_pipeline(strategy, mode="offline", store=MemoryVectorStore())


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_every_strategy_covers_every_document(strategy):
    reports = ingest_all(_pipeline(strategy))
    for report in reports:
        for doc_report in report.chunk_reports.values():
            assert doc_report["coverage"] == 1.0, f"{strategy} lost text: {doc_report}"
            assert doc_report["strategy"] == strategy


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_chunks_carry_loan_type_metadata(strategy):
    pipeline = _pipeline(strategy)
    ingest_all(pipeline)
    loan_types = {hit.chunk.metadata["loan_type"] for hit in pipeline.retriever.store.search(
        pipeline.embedder.embed_query("loan"), k=500)}
    assert loan_types == {"personal", "mortgage"}


def test_loan_type_filter_only_returns_that_loan_type():
    pipeline = _pipeline("markdown")
    ingest_all(pipeline)
    answer = ask(pipeline, "What is the early repayment charge on a fixed-rate mortgage?", loan_type="mortgage")
    assert answer.contexts, "filtered query returned nothing"
    assert all(h.chunk.metadata["loan_type"] == "mortgage" for h in answer.contexts)


def test_out_of_scope_question_is_refused():
    pipeline = _pipeline("markdown")
    ingest_all(pipeline)
    answer = ask(pipeline, "What is the interest rate on a car loan from Harbor Point Lending?")
    assert "do not know" in answer.answer.lower()


def test_load_config_sets_strategy_and_weaviate_collection():
    config = load_config("parent_child")
    assert config.chunking.strategy == "parent_child"
    assert config.vectorstore.backend == "weaviate"
    assert config.vectorstore.collection == "loanpenaltyparentchild"


def test_config_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        load_config("not_a_strategy")


def test_all_eight_metrics_are_configured_and_registered():
    config = load_config("recursive")
    assert sorted(config.evals.metrics) == sorted(ALL_METRICS)
    assert all(name in METRICS for name in ALL_METRICS)


def test_evaluation_scores_every_metric_on_every_question():
    pipeline = _pipeline("recursive")
    ingest_all(pipeline)
    samples = load_jsonl(QUESTIONS)
    report = pipeline.evaluate(samples)
    assert len(report.rows) == len(samples)
    assert set(report.summary) == set(ALL_METRICS)
    assert all(report.summary[m] is not None for m in ALL_METRICS)


def test_load_config_selects_pgvector_backend():
    config = load_config("markdown", backend="pgvector")
    assert config.vectorstore.backend == "pgvector"
    assert config.vectorstore.collection == "loanpenalty_markdown"
    assert config.vectorstore.options == {"dsn_env": "PGVECTOR_DSN", "schema": "public"}


def test_load_config_selects_weaviate_backend_and_drops_other_options():
    config = load_config("markdown", backend="weaviate")
    assert config.vectorstore.backend == "weaviate"
    assert "dsn_env" not in config.vectorstore.options
    assert "url" in config.vectorstore.options


def test_config_rejects_unknown_backend():
    with pytest.raises(ValueError):
        load_config("markdown", backend="chroma")


def test_pgvector_pipeline_ingests_and_answers_offline():
    pytest.importorskip("psycopg")
    dsn = os.environ.get("PGVECTOR_DSN")
    if not dsn:
        pytest.skip("Set PGVECTOR_DSN to run the pgvector pipeline test (for example docker compose --profile pgvector up)")
    pipeline = build_pipeline("markdown", mode="offline", reset=True, backend="pgvector")
    ingest_all(pipeline)
    answer = ask(pipeline, "What is the early repayment charge on a fixed-rate mortgage?", loan_type="mortgage")
    assert answer.contexts
    assert all(h.chunk.metadata["loan_type"] == "mortgage" for h in answer.contexts)
    pipeline.retriever.store.close()
