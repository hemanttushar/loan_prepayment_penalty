"""Command line for the loan prepayment penalty solution.

Examples:
    python run.py ingest --strategy markdown --backend pgvector
    python run.py ask "What is the penalty if repaid in month 20?" --strategy markdown
    python run.py evaluate --strategy parent_child
    python run.py compare                          # all six strategies, offline mode, Weaviate
    python run.py compare --backend pgvector       # same, on PostgreSQL + pgvector
    python run.py compare --mode live              # all six strategies, OpenAI models

The vector store is chosen with --backend (weaviate or pgvector). Without the flag, the
VECTOR_BACKEND environment variable is used, and that defaults to weaviate.
The chosen database must be running (see README.md). Set OPENROUTER_API_KEY for live mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepayment.settings import BACKENDS, DEFAULT_BACKEND, MODES, STRATEGIES, build_pipeline  # noqa: E402
from prepayment.solution import RESULTS_DIR, ask, compare, evaluate_strategy, ingest_all  # noqa: E402

BACKEND_HELP = "Vector store: weaviate or pgvector (default: $VECTOR_BACKEND, else weaviate)."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loan prepayment penalty solution on ragkit.")
    # --backend works before or after the command: run.py --backend pgvector compare, or compare --backend pgvector.
    parser.add_argument("--backend", choices=BACKENDS, default=None, help=BACKEND_HELP)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_backend(p):
        p.add_argument("--backend", choices=BACKENDS, default=argparse.SUPPRESS, help=BACKEND_HELP)

    def add_common(p):
        p.add_argument("--strategy", default="recursive", choices=STRATEGIES)
        p.add_argument("--mode", default="offline", choices=MODES)
        add_backend(p)

    p_ingest = sub.add_parser("ingest", help="Re-create the collection and index the documents.")
    add_common(p_ingest)

    p_ask = sub.add_parser("ask", help="Ask a question against the index.")
    p_ask.add_argument("question")
    p_ask.add_argument("--loan-type", choices=["personal", "mortgage"], help="Filter by loan type.")
    p_ask.add_argument("--no-ingest", action="store_true", help="Query the existing collection.")
    add_common(p_ask)

    p_eval = sub.add_parser("evaluate", help="Run all metrics for one strategy.")
    add_common(p_eval)

    p_cmp = sub.add_parser("compare", help="Run all metrics for all six chunking strategies.")
    p_cmp.add_argument("--mode", default="offline", choices=MODES)
    add_backend(p_cmp)

    args = parser.parse_args(argv)
    args.backend = getattr(args, "backend", None) or DEFAULT_BACKEND

    if args.command == "ingest":
        pipeline = build_pipeline(args.strategy, mode=args.mode, reset=True, backend=args.backend)
        reports = ingest_all(pipeline)
        print(json.dumps({"strategy": args.strategy, "backend": args.backend, "chunks": sum(r.chunks for r in reports)}))
        return 0

    if args.command == "ask":
        pipeline = build_pipeline(args.strategy, mode=args.mode, reset=not args.no_ingest, backend=args.backend)
        if not args.no_ingest:
            ingest_all(pipeline)
        answer = ask(pipeline, args.question, args.loan_type)
        print(answer.answer)
        for i, hit in enumerate(answer.contexts, start=1):
            meta = hit.chunk.metadata
            print(f"[{i}] {meta.get('document')} | {meta.get('section_path', meta.get('source'))} (score {hit.score:.3f})")
        return 0

    if args.command == "evaluate":
        result = evaluate_strategy(args.strategy, mode=args.mode, backend=args.backend)
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1

    if args.command == "compare":
        compare(mode=args.mode, backend=args.backend)
        print((RESULTS_DIR / f"comparison_{args.backend}_{args.mode}.md").read_text(encoding="utf-8"))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
