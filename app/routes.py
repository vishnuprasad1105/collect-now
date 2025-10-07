from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from werkzeug.utils import secure_filename

from . import db
from .document_processor import (analyze_document, is_allowed_file)
from .models import Transaction
from .chat_service import generate_response

bp = Blueprint("main", __name__)


@bp.route("/", methods=["GET", "POST"])
def index() -> str:
    if request.method == "POST":
        uploaded = request.files.get("document")
        if not uploaded or uploaded.filename == "":
            flash("Please choose a document to upload.", "error")
            return redirect(url_for("main.index", show_audit='true'))

        if not is_allowed_file(uploaded.filename):
            flash("Only PDF, DOCX, or DOC files are supported.", "error")
            return redirect(url_for("main.index", show_audit='true'))

        stored_filename = build_stored_filename(uploaded.filename)
        upload_path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_filename
        uploaded.save(upload_path)

        transaction = Transaction(
            stored_filename=stored_filename,
            original_filename=uploaded.filename,
            status="processing",
        )
        db.session.add(transaction)
        db.session.commit()

        result = analyze_document(
            upload_path,
            Path(current_app.config["RESOURCE_FOLDER"]),
        )
        
        # Use the to_dict method to store complete, serializable results
        analysis_data = result.to_dict()
        transaction.status = analysis_data["status"]
        transaction.checklist_results = json.dumps(analysis_data["checklist"])
        transaction.image_results = json.dumps(analysis_data["images"])
        transaction.processing_logs = "\n".join(analysis_data["logs"])
        transaction.response_payload = json.dumps(analysis_data["response_payload"])
        
        db.session.commit()

        # Flash a success message after processing
        flash(f"Successfully analyzed '{uploaded.filename}'.", "success")
        return redirect(url_for("main.transaction_detail", transaction_id=transaction.id))

    recent_transactions = (
        Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
    )
    return render_template("docs.html", transactions=recent_transactions)


@bp.route("/transactions/<int:transaction_id>")
def transaction_detail(transaction_id: int) -> str:
    transaction = Transaction.query.get_or_404(transaction_id)
    # Load the JSON data from the database for display
    checklist = json.loads(transaction.checklist_results or "{}")
    images = json.loads(transaction.image_results or "{}")

    return render_template(
        "transaction_detail.html",
        transaction=transaction,
        checklist=checklist,
        images=images,
    )


@bp.route("/api/chat", methods=["POST"])
def chat_endpoint():
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

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