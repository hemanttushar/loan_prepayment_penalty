"""Offline stand-in for the LLM: no API key, deterministic, and fast.

It answers ragkit's own prompts with simple word-overlap heuristics:

- answers: return the sentence in the best-matching context passage, or "I do not know" when
  nothing matches.
- judge prompts: return JSON that ragkit can parse. Each judgement is a word-overlap check.

These are heuristics for checking the wiring and comparing chunking strategies. They are not a
measure of answer quality. Use live mode (OpenAI) for real evaluation numbers.
"""

from __future__ import annotations

import json
import re
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")
_REFUSAL = "I do not know based on the provided documents."


# Words that appear in every document (bank name, titles, generic loan terms). Ignoring them stops
# a question like "car loan" from matching every passage just because it mentions the bank.
_GENERIC = {
    "harbor", "point", "lending", "home", "loan", "loans", "borrower", "lender", "bank", "personal",
    "mortgage", "template", "agreement", "terms", "customer", "document", "interest", "rate", "what",
    "does", "the", "and", "for", "from", "with", "that", "this", "must", "how", "much", "can", "any",
    "who", "is", "are", "was", "will", "not", "you", "your",
}


def _words(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text.lower()):
        w = w[:-1] if len(w) > 3 and w.endswith("s") else w  # crude plural stripping: months -> month
        if len(w) > 2 and w not in _GENERIC:
            out.add(w)
    return out


def _overlap(a: str, b: str) -> float:
    """Share of the words in ``a`` that also appear in ``b``."""
    wa = _words(a)
    return len(wa & _words(b)) / len(wa) if wa else 0.0


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _between(text: str, start: str, end: str) -> str:
    head = text.split(start, 1)[1] if start in text else text
    return head.split(end, 1)[0] if end in head else head


class OfflineLLM:
    """Implements ragkit's LLM protocol: ``complete(messages, json_mode=, temperature=) -> str``."""

    def complete(self, messages: list[dict[str, Any]], *, json_mode: bool = False, temperature=None) -> str:
        system = messages[0]["content"].lower()
        user = messages[-1]["content"]

        # Judge prompts from ragkit.evals.prompts, matched by distinctive phrases.
        if "break down each sentence" in system:
            answer = user.split("Answer: ", 1)[1]
            return json.dumps({"statements": _sentences(re.sub(r"\[\d+\]", "", answer))})

        if "faithfulness of each statement" in system:
            context = _between(user, "Context:\n", "\n\nQuestion:")
            statements = user.split("Statements:\n", 1)[1].splitlines()
            verdicts = [
                {"statement": s, "explanation": "word overlap", "rating": int(_overlap(s, context) >= 0.6)}
                for s in statements
                if s.strip()
            ]
            return json.dumps({"verdicts": verdicts})

        if "decide whether the passage was useful" in system:
            context = _between(user, "Context:\n", "\n\nQuestion:")
            answer = user.split("Answer: ", 1)[1]
            return json.dumps({"explanation": "word overlap", "rating": int(_overlap(answer, context) >= 0.3)})

        if "can be attributed to the context" in system:
            context = _between(user, "Context:\n", "\n\nAnswer:\n")
            target = user.split("\n\nAnswer:\n", 1)[1]
            rows = [
                {"sentence": s, "explanation": "word overlap", "rating": int(_overlap(s, context) >= 0.6)}
                for s in _sentences(target)
            ]
            return json.dumps({"classifications": rows})

        if "decide whether the answer is noncommittal" in system:
            answer = user.split("Answer: ", 1)[1]
            flag = bool(re.search(r"do not know|not sure|does not (cover|state|say)|not covered", answer, re.I))
            return json.dumps({"explanation": "refusal phrase", "non_committal_rating": int(flag)})

        if "generate the question that the given answer" in system:
            return json.dumps({"question": user.split("Answer: ", 1)[1]})

        if "impartial judge" in system:  # RAG Triad rater, 1-5
            context = _between(user, "###Context:\n", "\n\n###Question:")
            answer = user.split("###Answer:\n", 1)[1]
            score = _overlap(answer, context)
            rating = 5 if score >= 0.6 else 4 if score >= 0.4 else 3 if score >= 0.2 else 2
            return json.dumps({"explanation": "word overlap", "rating": rating})

        if json_mode:
            return "{}"

        # Answer generation: the grounded-answer prompt from ragkit.generation.
        question = user.rsplit("Question: ", 1)[-1].strip()
        q_words = _words(question)
        best: tuple[int, str] | None = None
        for index, passage in re.findall(r"\[(\d+)\] (.*?)(?=\n\n\[\d+\] |\n\nQuestion:)", user, re.S):
            for sentence in _sentences(passage):
                matches = len(q_words & _words(sentence))
                if best is None or matches > best[0]:
                    best = (matches, f"{sentence} [{index}]")
        if best is None or best[0] < 2:
            return _REFUSAL
        return best[1]
