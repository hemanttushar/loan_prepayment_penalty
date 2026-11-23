"""The solution: ingest the loan documents, answer questions, evaluate, and compare chunking strategies."""

from __future__ import annotations

import json
from pathlib import Path

from ragkit.evals.dataset import load_jsonl
from ragkit.pipeline import IngestReport, RAGPipeline
from ragkit.types import Answer

from prepayment.settings import DEFAULT_BACKEND, ROOT, STRATEGIES, build_pipeline

DATA_DIR = ROOT / "data"
QUESTIONS = ROOT / "evals" / "questions.jsonl"
RESULTS_DIR = ROOT / "results"

# Metadata per file. Stored with every chunk, so questions can be filtered by loan type.
DOCUMENTS = [
    {"file": "personal_loan_agreement.md", "loan_type": "personal", "document": "template v3.2"},
    {"file": "personal_loan_amendment_2024.html", "loan_type": "personal", "document": "amendment 2024-07"},
    {"file": "mortgage_terms.txt", "loan_type": "mortgage", "document": "terms 2023"},
]


def ingest_all(pipeline: RAGPipeline) -> list[IngestReport]:
    """Parse, chunk, embed and store every document in DOCUMENTS."""
    reports = []
    for doc in DOCUMENTS:
        metadata = {"loan_type": doc["loan_type"], "document": doc["document"]}
        reports.append(pipeline.ingest([DATA_DIR / doc["file"]], metadata=metadata))
    return reports


def ask(pipeline: RAGPipeline, question: str, loan_type: str | None = None) -> Answer:
    where = {"loan_type": loan_type} if loan_type else None
    return pipeline.query(question, where=where)


def _coverage(reports: list[IngestReport]) -> float:
    values = [r.get("coverage", 1.0) for rep in reports for r in rep.chunk_reports.values()]
    return round(sum(values) / len(values), 4) if values else 0.0


def evaluate_strategy(strategy: str, mode: str = "offline", backend: str = DEFAULT_BACKEND) -> dict:
    """Ingest into a fresh collection on the chosen backend, run every metric on every question, and report."""
    pipeline = build_pipeline(strategy, mode=mode, reset=True, backend=backend)
    reports = ingest_all(pipeline)
    samples = load_jsonl(QUESTIONS)  # fresh samples: evaluate() fills in answers and contexts
    out_dir = RESULTS_DIR / f"{backend}_{mode}_{strategy}"
    report = pipeline.evaluate(samples, out_dir=out_dir)
    return {
        "strategy": strategy,
        "backend": backend,
        "mode": mode,
        "chunks": sum(r.chunks for r in reports),
        "coverage": _coverage(reports),
        "summary": report.summary,
        "passed": report.passed,
        "failures": report.failures,
        "report_dir": str(out_dir),
    }


def compare(mode: str = "offline", backend: str = DEFAULT_BACKEND) -> list[dict]:
    """Run evaluate_strategy for every chunking strategy and write comparison_<backend>_<mode> files."""
    results = [evaluate_strategy(s, mode, backend) for s in STRATEGIES]
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"comparison_{backend}_{mode}"
    (RESULTS_DIR / f"{stem}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (RESULTS_DIR / f"{stem}.md").write_text(_markdown(results), encoding="utf-8")
    return results


def _markdown(results: list[dict]) -> str:
    metrics = list(results[0]["summary"].keys())
    header = "| strategy | chunks | coverage | " + " | ".join(metrics) + " |"
    rule = "|" + "---|" * (len(metrics) + 3)
    rows = []
    for r in results:
        cells = [_fmt(r["summary"].get(m)) for m in metrics]
        rows.append(f"| {r['strategy']} | {r['chunks']} | {r['coverage']} | " + " | ".join(cells) + " |")
    return "\n".join([header, rule, *rows]) + "\n"


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"
