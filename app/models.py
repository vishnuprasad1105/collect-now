from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from . import db


class Transaction(db.Model):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stored_filename: Mapped[str] = mapped_column(nullable=False)
    original_filename: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, default="processing")
    checklist_results: Mapped[str] = mapped_column(nullable=False, default="{}")
    image_results: Mapped[str] = mapped_column(nullable=False, default="{}")
    processing_logs: Mapped[str] = mapped_column(nullable=False, default="")
    request_payload: Mapped[str] = mapped_column(nullable=False, default="{}")
    response_payload: Mapped[str] = mapped_column(nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    def checklist_as_dict(self) -> dict:
        if not self.checklist_results:
            return {}
        from json import loads

        return loads(self.checklist_results)

    def images_as_dict(self) -> dict:
        if not self.image_results:
            return {}
        from json import loads

        return loads(self.image_results)

    def logs_as_list(self) -> list[str]:
        return [line for line in self.processing_logs.splitlines() if line]


class KnowledgeBaseEntry(db.Model):
    __tablename__ = "knowledge_base_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(nullable=False, unique=True)
    answer: Mapped[str] = mapped_column(nullable=False)
    tags: Mapped[str] = mapped_column(nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def tags_as_list(self) -> list[str]:
        if not self.tags:
            return []
        from json import loads

        try:
            return loads(self.tags)
        except Exception:
            return []
