# CollectNow Flask Analyzer

Automated document inspection utility for audit workflows. Upload PDF, DOCX, or legacy DOC evidence, extract key checklist confirmations, validate reference screenshots, and retain a persistent audit trail.

## Features

- Upload interface with HDFC CollectNow themed dashboard and processing timeline feedback
- Text extraction for PDF / DOCX / DOC with strict checklist validation and explicit `(YES)` enforcement
- Brand guardrails: verifies HDFC CollectNow mentions, colour palette, and Razorpay checkout embed URL
- OCR-backed screenshot analysis to confirm logo, checkout URL, payment success, and failure scenarios are documented
- API contract checks confirming mandatory request and response parameters in documented payloads
- SQLite-backed transaction ledger storing request / response payloads with rich audit trail
- Built-in knowledge base chatbot for answering CollectNow process questions from curated Q&A pairs

## Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env .env.local  # optional: customise secrets locally
```

Create the initial database and start the server:

```bash
flask --app run.py --debug run
```

## Project Layout

- `app/` – Flask application package
  - `document_processor.py` – text/image extraction and validation pipeline
  - `security_rules.py` – declarative checklist, text, and screenshot expectations
  - `models.py` – SQLAlchemy models
  - `templates/` – Jinja UI templates
  - `static/` – CSS and static assets
- `resources/` – drop reference images that must be present within uploads
- `uploads/` – processed documents stored with unique identifiers
- `instance/collectnow.sqlite` – generated SQLite database (created automatically)

## Usage Notes

1. Place expected reference images inside `resources/` before uploading documents.
2. Upload PDF, DOCX, or DOC evidence via the dashboard. A detailed result view lists checklist status, image matches, and processing timeline.
   - Legacy `.doc` parsing uses `textract`; ensure system prerequisites such as `antiword` are available. Image extraction from `.doc` files is currently skipped with a log notice.
3. If you capture bespoke screenshots, adjust `IMAGE_TEXT_EXPECTATIONS` in `app/security_rules.py` to reflect the phrases the analyzer should detect.
4. Install the Tesseract OCR binary (`brew install tesseract` on macOS, `sudo apt-get install tesseract-ocr` on Debian/Ubuntu) so the screenshot analysis can read on-screen text.
5. Populate the chatbot via `kb/knowledge_base.json` (see chatbot section) and run `python seed_kb.py` to sync entries.
6. Review stored request / response payloads per transaction for traceability.

Environment variables are loaded from `.env` automatically; adjust that file (or override via real environment values) for secrets such as `SECRET_KEY`, `OPENAI_API_KEY`, and matching thresholds.

## Visual Verification Rules

- Each PDF/DOC/DOCX page is scanned for embedded images; OCR is applied (via Tesseract) so the analyzer can read on-screen text.
- The rules in `app/security_rules.py` describe the required screenshots (branding/logo, Razorpay checkout embed URL, payment success, payment failure) and associated hints.
- Matches are reported with evidence snippets and the originating page, and missing checks highlight whether OCR or documentation failed to surface the expected wording.

## Chatbot Knowledge Base

- Edit `kb/knowledge_base.json` (or copy from `kb/sample_kb.json`) using an array of objects with `question`, `answer`, and optional `tags` keys.
- Run `python seed_kb.py` to upsert those entries into SQLite (`knowledge_base_entries` table).
- Provide an `OPENAI_API_KEY` environment variable to allow the assistant to restyle answers; otherwise the raw KB answer is returned.
- Optional: tune `KB_MATCH_THRESHOLD` (default 78) or `KB_AI_CANDIDATES` (default 25) via environment variables for stricter or broader matching.
- The chat button appears in the bottom-right corner of every page. It will only answer from the knowledge base; unmatched questions receive a polite fallback response.

## Checklist Targets

The analyzer enforces the following confirmations (each must explicitly contain `(YES)` in the document):

1. Maintain database to store the transaction details / status
2. Services / payment confirmation to customer / user provided based on database status
3. 7–8 transactions performed in Security Audit process
4. Login credentials available until audit completion
5. Database records not cleared before audit completion
6. UAT setup identical to production setup
7. Dual inquiry (Status API) implemented in response
8. Audit checklist implemented for integration and Security Audit processes

Green ticks signal success; unmet items surface missing keywords in red.
- `kb/` – JSON files for the chatbot knowledge base (`sample_kb.json` provided)
