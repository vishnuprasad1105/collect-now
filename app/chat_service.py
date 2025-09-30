from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Iterable, Sequence

from flask import current_app
from rapidfuzz import fuzz

from .models import KnowledgeBaseEntry

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except ImportError:  # pragma: no cover - gracefully handle missing SDK
    OpenAI = None  # type: ignore


@dataclass
class ChatResponse:
    answer: str
    source_question: str | None
    confidence: float
    used_ai: bool


def fetch_kb_entries() -> list[KnowledgeBaseEntry]:
    return KnowledgeBaseEntry.query.order_by(KnowledgeBaseEntry.id.asc()).all()


def find_best_match(question: str, entries: Iterable[KnowledgeBaseEntry]) -> tuple[KnowledgeBaseEntry | None, float]:
    best_entry: KnowledgeBaseEntry | None = None
    best_score = 0.0
    for entry in entries:
        score = combined_similarity(question, entry.question)
        if score > best_score:
            best_score = score
            best_entry = entry
    return best_entry, best_score


def combined_similarity(a: str, b: str) -> float:
    return max(
        fuzz.token_set_ratio(a, b),
        fuzz.partial_ratio(a, b),
        fuzz.QRatio(a, b),
    )


def generate_response(question: str) -> ChatResponse:
    entries = fetch_kb_entries()
    if not entries:
        return ChatResponse(
            answer="I don't have any knowledge base entries yet.",
            source_question=None,
            confidence=0.0,
            used_ai=False,
        )

    entry, score = find_best_match(question, entries)
    threshold = current_app.config.get("KB_MATCH_THRESHOLD", 78)

    refined_entry, refined_score, used_semantic = ai_refine_match(
        question, entries, entry, score, threshold
    )
    if refined_entry is not None:
        entry = refined_entry
        score = refined_score

    if entry is None or score < threshold:
        return ChatResponse(
            answer="I'm sorry, I don't have an answer for that yet.",
            source_question=None,
            confidence=score,
            used_ai=False,
        )

    formatted_answer = entry.answer.strip()

    ai_answer, used_ai = maybe_enhance_answer(question, entry.question, formatted_answer)
    used_ai = used_ai or used_semantic

    return ChatResponse(
        answer=ai_answer,
        source_question=entry.question,
        confidence=score,
        used_ai=used_ai,
    )


def maybe_enhance_answer(user_question: str, kb_question: str, kb_answer: str) -> tuple[str, bool]:
    client = _get_openai_client()
    if client is None:
        return kb_answer, False

    system_prompt = (
        "You are a precise assistant for the CollectNow application. "
        "Rewrite the provided knowledge base answer in clear, polished language without adding any new facts. "
        "If the answer is empty, respond with 'I'm sorry, I don't have an answer for that yet.'"
    )
    content = (
        "Knowledge Base Question: {kb_question}\n"
        "Knowledge Base Answer: {kb_answer}\n"
        "User Question: {user_question}\n"
        "Respond with a concise answer derived strictly from the knowledge base answer."
    ).format(kb_question=kb_question, kb_answer=kb_answer, user_question=user_question)

    try:  # pragma: no cover - network
        response = client.chat.completions.create(
            model=current_app.config.get("KB_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            temperature=0.0,
        )
        ai_answer = response.choices[0].message.content.strip()
        if not ai_answer:
            return kb_answer, False
        return ai_answer, True
    except Exception:
        # Fall back to KB answer if API fails or is unavailable
        return kb_answer, False


def _get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None
    try:
        client = OpenAI(api_key=api_key)
        _ensure_openai_healthcheck(client)
        return client
    except Exception:  # pragma: no cover - invalid key or init failure
        current_app.logger.warning("OpenAI client could not be initialised; check OPENAI_API_KEY.")
        return None


def _ensure_openai_healthcheck(client: OpenAI) -> None:
    if current_app is None:
        return
    if current_app.config.get("OPENAI_HEALTHCHECK_DONE"):
        return
    try:  # pragma: no cover - network
        client.models.list(limit=1)
        current_app.logger.info("OpenAI connectivity check succeeded.")
    except Exception as exc:
        current_app.logger.warning("OpenAI connectivity check failed: %s", exc)
    finally:
        current_app.config["OPENAI_HEALTHCHECK_DONE"] = True


def ai_refine_match(
    question: str,
    entries: Sequence[KnowledgeBaseEntry],
    initial_entry: KnowledgeBaseEntry | None,
    initial_score: float,
    threshold: int,
) -> tuple[KnowledgeBaseEntry | None, float, bool]:
    client = _get_openai_client()
    if client is None or not entries:
        return initial_entry, initial_score, False

    top_n = current_app.config.get("KB_AI_CANDIDATES", 25)

    candidate_entries: list[KnowledgeBaseEntry] = []
    seen_ids: set[int] = set()

    if initial_entry is not None:
        candidate_entries.append(initial_entry)
        seen_ids.add(initial_entry.id)

    if initial_entry is None or initial_score < threshold or len(entries) <= top_n:
        for entry in entries:
            if entry.id not in seen_ids:
                candidate_entries.append(entry)
                seen_ids.add(entry.id)
    else:
        sorted_entries = sorted(
            entries,
            key=lambda e: combined_similarity(question, e.question),
            reverse=True,
        )
        for entry in sorted_entries:
            if entry.id not in seen_ids:
                candidate_entries.append(entry)
                seen_ids.add(entry.id)
            if len(candidate_entries) >= top_n:
                break

    catalog = [
        {
            "id": idx,
            "question": entry.question,
            "answer": entry.answer,
        }
        for idx, entry in enumerate(candidate_entries)
    ]

    prompt = (
        "You are a retrieval assistant. Pick the single knowledge base question that best matches the user's intent.\n"
        "If none of the knowledge base entries answer the user, respond with JSON {\"match\": null}.\n"
        "Otherwise respond with JSON {\"match\": <id>} using the provided id.\n"
        "Never invent new answers.\n"
        f"User question: {question}\n"
        f"Knowledge base entries: {json.dumps(catalog, ensure_ascii=False)}"
    )

    try:  # pragma: no cover - network
        response = client.chat.completions.create(
            model=current_app.config.get("KB_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        content = response.choices[0].message.content or ""
        match_payload = json.loads(content)
        match_id = match_payload.get("match")
        if match_id is None:
            return initial_entry, initial_score, True
        if not isinstance(match_id, int) or match_id >= len(candidate_entries):
            return initial_entry, initial_score, True
        entry = candidate_entries[match_id]
        score = max(combined_similarity(question, entry.question), float(threshold))
        return entry, score, True
    except Exception:
        return initial_entry, initial_score, False
