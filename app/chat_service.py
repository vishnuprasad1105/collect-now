from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from flask import current_app
from rapidfuzz import fuzz

from .models import KnowledgeBaseEntry

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


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

    client = _get_openai_client()
    
    # STEP 1: Use AI to understand and refine the user's question intent
    refined_question, intent_extraction_used_ai = extract_question_intent(client, question)
    
    # STEP 2: Try fuzzy matching first
    entry, score = find_best_match(refined_question or question, entries)
    threshold = current_app.config.get("KB_MATCH_THRESHOLD", 78)

    # STEP 3: Use AI semantic matching to find the best KB entry
    refined_entry, refined_score, used_semantic = ai_semantic_match(
        client, refined_question or question, entries, entry, score, threshold
    )
    
    if refined_entry is not None:
        entry = refined_entry
        score = refined_score

    if entry is None or score < threshold:
        return ChatResponse(
            answer="I'm sorry, I don't have an answer for that question in my knowledge base. Please try rephrasing or contact support for assistance.",
            source_question=None,
            confidence=score,
            used_ai=intent_extraction_used_ai or used_semantic,
        )

    # STEP 4: Format and enhance the answer with AI
    formatted_answer, formatting_used_ai = format_answer_with_ai(
        client, 
        user_question=question,
        kb_question=entry.question, 
        kb_answer=entry.answer
    )
    
    used_ai = intent_extraction_used_ai or used_semantic or formatting_used_ai

    return ChatResponse(
        answer=formatted_answer,
        source_question=entry.question,
        confidence=score,
        used_ai=used_ai,
    )


def extract_question_intent(client, user_question: str) -> tuple[str | None, bool]:
    """Use AI to extract the core intent and rephrase the question for better matching."""
    if client is None:
        return None, False
    
    system_prompt = """You are a question analysis expert for HDFC CollectNow payment integration system.
Your task is to extract the core intent from user questions and rephrase them clearly.

Identify key concepts like:
- API integration, endpoints, webhooks
- Payment flows, transaction status
- Database requirements, audit requirements
- Security checklist items
- Error handling, failure scenarios
- Razorpay integration specifics

Respond with a JSON object:
{
  "refined_question": "clear, concise question capturing the core intent",
  "key_concepts": ["concept1", "concept2"],
  "question_type": "technical|process|troubleshooting|compliance"
}"""

    try:
        response = client.chat.completions.create(
            model=current_app.config.get("KB_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this question: {user_question}"},
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        refined = result.get("refined_question", user_question)
        current_app.logger.info(f"Question refined: '{user_question}' -> '{refined}'")
        return refined, True
    except Exception as e:
        current_app.logger.warning(f"Question intent extraction failed: {e}")
        return None, False


def ai_semantic_match(
    client,
    question: str,
    entries: Sequence[KnowledgeBaseEntry],
    initial_entry: KnowledgeBaseEntry | None,
    initial_score: float,
    threshold: int,
) -> tuple[KnowledgeBaseEntry | None, float, bool]:
    """Use AI to find the most semantically relevant KB entry."""
    if client is None or not entries:
        return initial_entry, initial_score, False

    top_n = min(current_app.config.get("KB_AI_CANDIDATES", 25), len(entries))

    # Build candidate list
    candidate_entries: list[KnowledgeBaseEntry] = []
    seen_ids: set[int] = set()

    if initial_entry is not None:
        candidate_entries.append(initial_entry)
        seen_ids.add(initial_entry.id)

    # Add top fuzzy matches
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
            "answer": entry.answer[:300] + "..." if len(entry.answer) > 300 else entry.answer,
            "tags": json.loads(entry.tags) if entry.tags else []
        }
        for idx, entry in enumerate(candidate_entries)
    ]

    system_prompt = """You are a semantic search expert for HDFC CollectNow knowledge base.
Analyze the user's question and find the BEST matching knowledge base entry.

Consider:
- Semantic similarity (same meaning, different words)
- Technical context and domain knowledge
- Question intent and user needs

Respond with JSON:
{
  "match": <id of best entry or null if none match>,
  "confidence": <0-100 score>,
  "reasoning": "brief explanation of why this entry matches"
}

If no entry adequately answers the question, return {"match": null, "confidence": 0}."""

    prompt = f"""User question: {question}

Knowledge base entries:
{json.dumps(catalog, indent=2, ensure_ascii=False)}

Find the best match."""

    try:
        response = client.chat.completions.create(
            model=current_app.config.get("KB_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content or ""
        match_payload = json.loads(content)
        match_id = match_payload.get("match")
        ai_confidence = match_payload.get("confidence", 0)
        reasoning = match_payload.get("reasoning", "")
        
        current_app.logger.info(f"AI match reasoning: {reasoning}")
        
        if match_id is None:
            return initial_entry, initial_score, True
            
        if not isinstance(match_id, int) or match_id >= len(candidate_entries):
            return initial_entry, initial_score, True
            
        entry = candidate_entries[match_id]
        # Boost score if AI is confident
        score = max(combined_similarity(question, entry.question), float(threshold), ai_confidence)
        
        return entry, score, True
    except Exception as e:
        current_app.logger.warning(f"AI semantic matching failed: {e}")
        return initial_entry, initial_score, False


def format_answer_with_ai(
    client,
    user_question: str,
    kb_question: str,
    kb_answer: str
) -> tuple[str, bool]:
    """Use AI to format the answer with proper structure, formatting URLs, code, JSON, etc."""
    if client is None:
        return format_answer_basic(kb_answer), False

    system_prompt = """You are a helpful assistant for HDFC CollectNow payment integration system.

Your task is to take a knowledge base answer and format it beautifully for the user.

Guidelines:
1. Keep all factual information from the KB answer - do not add new facts
2. Format URLs as clickable links: [Link Text](URL)
3. Format code snippets with proper markdown: ```language\\ncode\\n```
4. Format JSON with proper indentation and markdown: ```json\\n{...}\\n```
5. Use bullet points and numbered lists for clarity
6. Bold important terms and concepts
7. Add clear section headers if the answer has multiple parts
8. Make the response conversational and easy to understand
9. If there are API endpoints, parameters, or technical details, structure them clearly
10. Keep the response concise but complete

If the KB answer contains references like "see documentation" or URLs, preserve and format them properly."""

    user_prompt = f"""User asked: "{user_question}"

KB Question: "{kb_question}"

KB Answer:
{kb_answer}

Format this answer to be clear, well-structured, and easy to read. Include all information from the KB answer."""

    try:
        response = client.chat.completions.create(
            model=current_app.config.get("KB_OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        
        formatted = response.choices[0].message.content.strip()
        
        if not formatted:
            return format_answer_basic(kb_answer), False
            
        return formatted, True
    except Exception as e:
        current_app.logger.warning(f"AI answer formatting failed: {e}")
        return format_answer_basic(kb_answer), False


def format_answer_basic(answer: str) -> str:
    """Basic formatting fallback when AI is unavailable."""
    # Detect and format URLs
    url_pattern = r'(https?://[^\s]+)'
    answer = re.sub(url_pattern, r'[\1](\1)', answer)
    
    # Detect JSON blocks and add code formatting
    if '{' in answer and '}' in answer:
        try:
            # Try to identify JSON blocks
            lines = answer.split('\n')
            formatted_lines = []
            in_json = False
            json_buffer = []
            
            for line in lines:
                if '{' in line and not in_json:
                    in_json = True
                    json_buffer = [line]
                elif in_json:
                    json_buffer.append(line)
                    if '}' in line:
                        json_text = '\n'.join(json_buffer)
                        try:
                            parsed = json.loads(json_text)
                            formatted_json = json.dumps(parsed, indent=2)
                            formatted_lines.append(f"```json\n{formatted_json}\n```")
                        except:
                            formatted_lines.extend(json_buffer)
                        in_json = False
                        json_buffer = []
                else:
                    formatted_lines.append(line)
            
            answer = '\n'.join(formatted_lines)
        except:
            pass
    
    return answer


def _get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return None
    try:
        client = OpenAI(api_key=api_key)
        _ensure_openai_healthcheck(client)
        return client
    except Exception:
        current_app.logger.warning("OpenAI client could not be initialised; check OPENAI_API_KEY.")
        return None


def _ensure_openai_healthcheck(client: OpenAI) -> None:
    if current_app is None:
        return
    if current_app.config.get("OPENAI_HEALTHCHECK_DONE"):
        return
    try:
        client.models.list(limit=1)
        current_app.logger.info("OpenAI connectivity check succeeded.")
    except Exception as exc:
        current_app.logger.warning("OpenAI connectivity check failed: %s", exc)
    finally:
        current_app.config["OPENAI_HEALTHCHECK_DONE"] = True