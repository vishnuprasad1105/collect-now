from __future__ import annotations

import json
from pathlib import Path

from flask import Flask

from app import create_app, db
from app.models import KnowledgeBaseEntry

KB_PATH = Path("kb/knowledge_base.json")
DEFAULT_SAMPLE = Path("kb/sample_kb.json")


def load_entries(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Knowledge base file not found: {path}. Create it or copy {DEFAULT_SAMPLE}."
        )
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Knowledge base file must contain a list of entries.")
    return data


def upsert_entry(entry: dict) -> None:
    question = entry.get("question", "").strip()
    answer = entry.get("answer", "").strip()
    tags = entry.get("tags", [])

    if not question or not answer:
        raise ValueError(f"Invalid entry detected: {entry}")

    tags_json = json.dumps(tags, ensure_ascii=False)

    existing = KnowledgeBaseEntry.query.filter_by(question=question).first()
    if existing:
        existing.answer = answer
        existing.tags = tags_json
    else:
        db.session.add(
            KnowledgeBaseEntry(question=question, answer=answer, tags=tags_json)
        )


def main() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
     #   entries = load_entries(KB_PATH if KB_PATH.exists() else DEFAULT_SAMPLE)
        entries = load_entries(DEFAULT_SAMPLE)
        for entry in entries:
            upsert_entry(entry)
        db.session.commit()
    print(f"Loaded {len(entries)} knowledge base entries.")


if __name__ == "__main__":
    main()
