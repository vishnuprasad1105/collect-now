from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from werkzeug.utils import secure_filename

from . import db
from .document_processor import (analyze_document, is_allowed_file,
                                  to_json)
from .models import Transaction
from .chat_service import generate_response

bp = Blueprint("main", __name__)


@bp.route("/", methods=["GET", "POST"])
def index() -> str:
    if request.method == "POST":
        uploaded = request.files.get("document")
        if not uploaded or uploaded.filename == "":
            flash("Please choose a document to upload.", "error")
            return redirect(url_for("main.index"))

        if not is_allowed_file(uploaded.filename):
            flash("Only PDF, DOCX, or DOC files are supported.", "error")
            return redirect(url_for("main.index"))

        stored_filename = build_stored_filename(uploaded.filename)
        upload_path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_filename
        uploaded.save(upload_path)

        transaction = Transaction(
            stored_filename=stored_filename,
            original_filename=uploaded.filename,
            status="processing",
            request_payload=json.dumps(
                {
                    "filename": uploaded.filename,
                    "timestamp": datetime.utcnow().isoformat(),
                    "content_type": uploaded.mimetype,
                }
            ),
        )
        db.session.add(transaction)
        db.session.commit()

        result = analyze_document(
            upload_path,
            Path(current_app.config["RESOURCE_FOLDER"]),
        )

        transaction.status = result.status
        transaction.checklist_results = to_json(result.checklist)
        transaction.image_results = to_json(result.images)
        transaction.processing_logs = "\n".join(result.logs)
        transaction.response_payload = json.dumps(result.response_payload)

        db.session.commit()

        message_category = "success" if result.status == "passed" else "error"
        flash(f"Analysis complete: {result.status.upper()}", message_category)
        return redirect(url_for("main.transaction_detail", transaction_id=transaction.id))

    recent_transactions = (
        Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
    )
    return render_template("home.html", transactions=recent_transactions)


@bp.route("/transactions/<int:transaction_id>")
def transaction_detail(transaction_id: int) -> str:
    transaction = Transaction.query.get_or_404(transaction_id)
    checklist = transaction.checklist_as_dict()
    images = transaction.images_as_dict()
    logs = transaction.logs_as_list()
    response_payload = json.loads(transaction.response_payload or "{}")

    return render_template(
        "transaction_detail.html",
        transaction=transaction,
        checklist=checklist,
        images=images,
        logs=logs,
        response_payload=response_payload,
    )


@bp.route("/api/chat", methods=["POST"])
def chat_endpoint():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({
            "error": "Question is required.",
        }), 400

    response = generate_response(question)
    return jsonify(
        {
            "answer": response.answer,
            "source_question": response.source_question,
            "confidence": response.confidence,
            "used_ai": response.used_ai,
        }
    )


def build_stored_filename(filename: str) -> str:
    name = secure_filename(Path(filename).stem)
    suffix = Path(filename).suffix
    token = secrets.token_hex(4)
    return f"{name}-{token}{suffix}"
