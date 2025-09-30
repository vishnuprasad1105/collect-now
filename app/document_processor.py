from __future__ import annotations

import io
import json
import mimetypes
import re
import textwrap
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pdfplumber
import fitz  # type: ignore[import]
from PIL import Image
from docx import Document
from rapidfuzz import fuzz

pytesseract = None

try:
    import textract  # type: ignore[import]
except ImportError:  # pragma: no cover - optional dependency
    textract = None

from .security_rules import (
    ADDITIONAL_TEXT_EXPECTATIONS,
    BASE_CHECKLIST_RULES,
    IMAGE_TEXT_EXPECTATIONS,
    REQUEST_REQUIRED_FIELDS,
    RESPONSE_REQUIRED_FIELDS,
    ChecklistRule,
    FieldBundle,
    ImageTextExpectation,
)


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


@dataclass
class ProcessingResult:
    checklist: dict
    images: dict
    logs: list[str]
    status: str
    response_payload: dict


@dataclass
class ExtractedImage:
    image: Image.Image
    origin: str


def normalize_line(line: str) -> str:
    cleaned = re.sub(r"[\u2010-\u2015]", "-", line)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip().lower()


def build_line_variants(line: str) -> tuple[str, str]:
    normalized = normalize_line(line)
    compact = normalized.replace(" ", "")
    return normalized, compact


def build_document_variants(line_variants: list[tuple[str, str]]) -> tuple[str, str]:
    joined = " ".join(variant[0] for variant in line_variants)
    compact = "".join(variant[1] for variant in line_variants)
    return joined, compact


def keyword_variants(keyword: str) -> tuple[str, str]:
    normalized = normalize_line(keyword)
    compact = normalized.replace(" ", "")
    return normalized, compact


def keyword_in_variants(variants: tuple[str, str], keyword: str) -> bool:
    normalized, compact = keyword_variants(keyword)
    if normalized in variants[0] or compact in variants[1]:
        return True
    return fuzz.partial_ratio(normalized, variants[0]) >= 80


def document_contains_keyword(document_variants: tuple[str, str], keyword: str) -> bool:
    normalized, compact = keyword_variants(keyword)
    if normalized in document_variants[0] or compact in document_variants[1]:
        return True
    return fuzz.partial_ratio(normalized, document_variants[0]) >= 80


def line_has_yes(variants: tuple[str, str]) -> bool:
    return "yes" in variants[0] or "yes" in variants[1] or fuzz.partial_ratio("yes", variants[0]) >= 80


def find_context_index(
    line_variants: list[tuple[str, str]],
    keywords: Iterable[str] = (),
    optional_keywords: Iterable[str] = (),
) -> int | None:
    keyword_list = list(keywords)
    optional_list = list(optional_keywords)

    for index, variants in enumerate(line_variants):
        if keyword_list and not all(keyword_in_variants(variants, keyword) for keyword in keyword_list):
            continue
        if optional_list and not any(
            keyword_in_variants(variants, keyword) for keyword in optional_list
        ):
            continue
        if not keyword_list and optional_list:
            if not any(keyword_in_variants(variants, keyword) for keyword in optional_list):
                continue
        return index
    return None


def is_allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def analyze_document(file_path: Path, resource_dir: Path) -> ProcessingResult:
    logs: list[str] = [f"Starting analysis for {file_path.name}"]
    text_lines = extract_text_lines(file_path, logs)
    logs.append(f"Extracted {len(text_lines)} text lines")

    extracted_images = extract_images(file_path, logs)
    image_text_entries: list[dict] = []
    for idx, payload in enumerate(extracted_images, start=1):
        text = extract_text_from_image_payload(payload, logs)
        if text:
            image_text_entries.append(
                {
                    "origin": payload.origin,
                    "index": idx,
                    "text": text,
                }
            )

    if image_text_entries:
        logs.append(f"OCR extracted text from {len(image_text_entries)} image(s)")
    elif extracted_images:
        logs.append("Images detected but no OCR text produced (check Tesseract installation)")

    image_lines: list[str] = []
    for entry in image_text_entries:
        for raw_line in entry["text"].splitlines():
            line = raw_line.strip()
            if line:
                image_lines.append(line)

    combined_lines = text_lines + image_lines

    line_variants = [build_line_variants(line) for line in combined_lines]
    document_variants = build_document_variants(line_variants)

    checklist_results = evaluate_checklist(combined_lines, line_variants, document_variants, logs)
    text_expectations = evaluate_text_expectations(combined_lines, line_variants, document_variants, logs)
    request_contract = evaluate_field_bundle(
        REQUEST_REQUIRED_FIELDS,
        combined_lines,
        line_variants,
        document_variants,
        logs,
    )
    response_contract = evaluate_field_bundle(
        RESPONSE_REQUIRED_FIELDS,
        combined_lines,
        line_variants,
        document_variants,
        logs,
    )

    combined_results: OrderedDict[str, dict] = OrderedDict()
    combined_results.update(checklist_results)
    combined_results.update(text_expectations)
    combined_results.update(request_contract)
    combined_results.update(response_contract)

    image_matches = evaluate_image_text_expectations(image_text_entries, document_variants, logs)

    status = "passed"
    for item in combined_results.values():
        if not item["passed"]:
            status = "failed"
            break
    if status == "passed":
        unmet = [m for m in image_matches.values() if not m.get("matched")]
        if unmet:
            status = "failed"

    category_breakdown: dict[str, dict[str, int]] = {}
    for item in combined_results.values():
        category = item.get("category", "general")
        stats = category_breakdown.setdefault(category, {"total": 0, "passed": 0})
        stats["total"] += 1
        if item.get("passed"):
            stats["passed"] += 1

    response_payload = {
        "file": file_path.name,
        "checklist": combined_results,
        "images": image_matches,
        "summary": {
            "total_checks": len(combined_results),
            "checks_passed": sum(1 for item in combined_results.values() if item["passed"]),
            "references": len(image_matches),
            "references_matched": sum(1 for item in image_matches.values() if item.get("matched")),
            "category_breakdown": category_breakdown,
        },
    }

    logs.append(f"Analysis completed with status: {status.upper()}")

    return ProcessingResult(
        checklist=combined_results,
        images=image_matches,
        logs=logs,
        status=status,
        response_payload=response_payload,
    )


def extract_text_lines(file_path: Path, logs: list[str]) -> list[str]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_lines_pdf(file_path, logs)
    if suffix == ".docx":
        return extract_text_lines_docx(file_path, logs)
    if suffix == ".doc":
        return extract_text_lines_doc(file_path, logs)
    logs.append(f"Unsupported file type for text extraction: {suffix}")
    return []


def extract_text_lines_pdf(file_path: Path, logs: list[str]) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            for raw_line in page_text.splitlines():
                line = raw_line.strip()
                if line:
                    lines.append(line)
                    logs.append(f"[Page {page_number}] {line}")
    return lines


def extract_text_lines_docx(file_path: Path, logs: list[str]) -> list[str]:
    lines: list[str] = []
    document = Document(file_path)
    for paragraph in document.paragraphs:
        line = paragraph.text.strip()
        if line:
            lines.append(line)
            logs.append(f"[Paragraph] {line}")
    return lines


def extract_text_lines_doc(file_path: Path, logs: list[str]) -> list[str]:
    if textract is None:
        logs.append("textract dependency missing; unable to parse legacy .doc document")
        return []

    try:
        raw_bytes = textract.process(str(file_path), extension="doc")
    except Exception as exc:  # pragma: no cover - external tool failure
        logs.append(f"Failed to extract text from .doc: {exc}")
        return []

    decoded = raw_bytes.decode("utf-8", errors="ignore")
    lines: list[str] = []
    for raw_line in decoded.splitlines():
        line = raw_line.strip()
        if line:
            lines.append(line)
            logs.append(f"[DOC] {line}")
    return lines


def evaluate_checklist(
    original_lines: list[str],
    line_variants: list[tuple[str, str]],
    document_variants: tuple[str, str],
    logs: list[str],
) -> OrderedDict[str, dict]:
    results: OrderedDict[str, dict] = OrderedDict()
    for rule in BASE_CHECKLIST_RULES:
        context_index = find_context_index(line_variants, rule.keywords_all)
        context_line = original_lines[context_index] if context_index is not None else None

        missing_keywords: list[str] = []
        found_keywords: list[str] = []

        if context_index is not None:
            variants = line_variants[context_index]
            for keyword in rule.keywords_all:
                if keyword_in_variants(variants, keyword):
                    found_keywords.append(keyword)
                elif document_contains_keyword(document_variants, keyword):
                    found_keywords.append(keyword)
                else:
                    missing_keywords.append(keyword)
            if rule.require_yes and not line_has_yes(variants):
                missing_keywords.append("yes")
        else:
            for keyword in rule.keywords_all:
                if document_contains_keyword(document_variants, keyword):
                    found_keywords.append(keyword)
                else:
                    missing_keywords.append(keyword)
            if rule.require_yes:
                missing_keywords.append("yes")

        passed = len(missing_keywords) == 0
        status = "PASSED" if passed else "FAILED"
        logs.append(f"Checklist item '{rule.label}' => {status}")

        results[rule.id] = {
            "label": rule.label,
            "passed": passed,
            "found_keywords": sorted(set(found_keywords)),
            "missing_keywords": sorted(set(missing_keywords)),
            "category": rule.category,
            "hint": rule.hint,
            "context": context_line or "",
        }

    return results


def evaluate_text_expectations(
    original_lines: list[str],
    line_variants: list[tuple[str, str]],
    document_variants: tuple[str, str],
    logs: list[str],
) -> OrderedDict[str, dict]:
    results: OrderedDict[str, dict] = OrderedDict()
    for expectation in ADDITIONAL_TEXT_EXPECTATIONS:
        missing_keywords: list[str] = []
        found_keywords: list[str] = []

        for keyword in expectation.keywords_all:
            if document_contains_keyword(document_variants, keyword):
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)

        any_found: list[str] = []
        if expectation.keywords_any:
            any_found = [
                keyword
                for keyword in expectation.keywords_any
                if document_contains_keyword(document_variants, keyword)
            ]
            if not any_found:
                missing_keywords.extend(expectation.keywords_any)
            else:
                found_keywords.extend(any_found)

        context_index = find_context_index(
            line_variants,
            expectation.keywords_all,
            expectation.keywords_any,
        )
        context_line = original_lines[context_index] if context_index is not None else None

        passed = len(missing_keywords) == 0
        status = "PASSED" if passed else "FAILED"
        logs.append(f"Text expectation '{expectation.label}' => {status}")

        results[expectation.id] = {
            "label": expectation.label,
            "passed": passed,
            "found_keywords": sorted(set(found_keywords)),
            "missing_keywords": sorted(set(missing_keywords)),
            "category": expectation.category,
            "hint": expectation.hint,
            "context": context_line or "",
        }

    return results


def evaluate_field_bundle(
    bundle: FieldBundle,
    original_lines: list[str],
    line_variants: list[tuple[str, str]],
    document_variants: tuple[str, str],
    logs: list[str],
) -> OrderedDict[str, dict]:
    missing: list[str] = []
    found: list[str] = []

    for field in bundle.fields:
        if document_contains_keyword(document_variants, field):
            found.append(field)
        else:
            missing.append(field)

    context_index = find_context_index(line_variants, optional_keywords=bundle.fields)
    context_line = original_lines[context_index] if context_index is not None else None

    passed = len(missing) == 0
    status = "PASSED" if passed else "FAILED"
    logs.append(f"Payload expectation '{bundle.label}' => {status}")

    result = OrderedDict(
        [
            (
                bundle.id,
                {
                    "label": bundle.label,
                    "passed": passed,
                    "found_keywords": sorted(set(found)),
                    "missing_keywords": sorted(set(missing)),
                    "category": bundle.category,
                    "hint": bundle.hint,
                    "context": context_line or "",
                },
            )
        ]
    )
    return result


def extract_images(file_path: Path, logs: list[str]) -> list[ExtractedImage]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return extract_images_pdf(file_path, logs)
    if suffix == ".docx":
        return extract_images_docx(file_path, logs)
    if suffix == ".doc":
        return extract_images_doc(file_path, logs)
    return []


def extract_images_pdf(file_path: Path, logs: list[str]) -> list[ExtractedImage]:
    images: list[ExtractedImage] = []
    document = fitz.open(file_path)
    for page_num in range(len(document)):
        page = document[page_num]
        for image_index, img_info in enumerate(page.get_images(full=True), start=1):
            xref = img_info[0]
            base_image = document.extract_image(xref)
            image_bytes = base_image.get("image")
            if not image_bytes:
                continue
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            origin = f"PDF page {page_num + 1} · image {image_index}"
            images.append(ExtractedImage(image=image, origin=origin))
            logs.append(f"Extracted image {image_index} from page {page_num + 1}")
    return images


def extract_images_docx(file_path: Path, logs: list[str]) -> list[ExtractedImage]:
    images: list[ExtractedImage] = []
    with zipfile.ZipFile(file_path) as archive:
        for name in archive.namelist():
            if name.startswith("word/media/"):
                data = archive.read(name)
                try:
                    image = Image.open(io.BytesIO(data)).convert("RGB")
                    origin = f"DOCX asset {name}"
                    images.append(ExtractedImage(image=image, origin=origin))
                    logs.append(f"Extracted image from {name}")
                except Exception:  # pragma: no cover - corrupted image fallback
                    logs.append(f"Failed to decode image {name}")
    return images


def extract_images_doc(file_path: Path, logs: list[str]) -> list[ExtractedImage]:
    logs.append("Binary .doc image extraction not supported; skipping visual validation")
    return []


def extract_text_from_image_payload(payload: ExtractedImage, logs: list[str]) -> str:
    ocr = resolve_ocr()
    if ocr is None:
        logs.append("pytesseract not installed; unable to OCR " + payload.origin)
        try:
            payload.image.close()
        except Exception:
            pass
        return ""

    try:
        text = ocr.image_to_string(payload.image)
    except Exception as exc:  # pragma: no cover - OCR failure
        logs.append(f"OCR failed for {payload.origin}: {exc}")
        return ""
    finally:
        try:
            payload.image.close()
        except Exception:
            pass

    cleaned = text.strip()
    if cleaned:
        snippet = textwrap.shorten(cleaned.replace("\n", " "), width=140)
        logs.append(f"[Image OCR] {payload.origin}: {snippet}")
    else:
        logs.append(f"[Image OCR] {payload.origin}: (no text detected)")
    return cleaned


def evaluate_image_text_expectations(
    image_text_entries: list[dict],
    document_variants: tuple[str, str],
    logs: list[str],
) -> dict[str, dict]:
    results: dict[str, dict] = {}

    normalized_entries: list[dict] = []
    for entry in image_text_entries:
        normalized_entries.append(
            {
                "origin": entry["origin"],
                "index": entry["index"],
                "text": entry["text"],
                "normalized": normalize_line(entry["text"]),
            }
        )

    combined_image_text = " ".join(item["normalized"] for item in normalized_entries)
    if image_text_entries and combined_image_text:
        logs.append(
            f"Aggregated OCR text length: {len(combined_image_text)} characters across {len(image_text_entries)} images"
        )
    if not image_text_entries:
        logs.append("No OCR text extracted from images; visual checks may be incomplete")

    for expectation in IMAGE_TEXT_EXPECTATIONS:
        matches: list[dict] = []
        for entry in normalized_entries:
            if image_text_satisfies_expectation(expectation, entry["normalized"]):
                snippet = textwrap.shorten(
                    entry["text"].replace("\n", " "),
                    width=160,
                    placeholder="…",
                )
                matches.append(
                    {
                        "origin": entry["origin"],
                        "index": entry["index"],
                        "snippet": snippet,
                    }
                )

        matched = bool(matches)
        fallback_context = False
        if not matched and expectation.apply_document_fallback:
            matched = image_text_satisfies_expectation(expectation, document_variants[0])
            fallback_context = matched

        analysis: dict[str, object] = {
            "requirements_met": matched,
            "description": expectation.description,
        }
        if matches:
            analysis["evidence"] = matches
        if expectation.hint:
            analysis["hint"] = expectation.hint
        if fallback_context and not matches:
            analysis["note"] = "Matched via document text fallback (no OCR evidence)."
        if not matched:
            reason = "Condition not met in image OCR output"
            if resolve_ocr() is None:
                reason = "OCR unavailable (install Tesseract)"
            analysis["reason"] = reason

        results[expectation.id] = {
            "matched": matched,
            "score": None,
            "hash_distance": None,
            "label": expectation.label,
            "reference_file": None,
            "analysis": analysis,
            "expectation": expectation.description,
            "expectation_id": expectation.id,
        }

        status = "MATCH" if matched else "NO MATCH"
        logs.append(f"Visual expectation '{expectation.label}' => {status}")
        if matches:
            for evidence in matches:
                logs.append(
                    f"  · Evidence from {evidence['origin']}: {evidence['snippet']}"
                )

    return results


def image_text_satisfies_expectation(expectation: ImageTextExpectation, text: str) -> bool:
    if not text:
        return False

    if expectation.keywords_all:
        for keyword in expectation.keywords_all:
            if fuzz.partial_ratio(keyword, text) < expectation.threshold_all:
                return False

    if expectation.keywords_any:
        for keyword in expectation.keywords_any:
            if fuzz.partial_ratio(keyword, text) >= expectation.threshold_any:
                break
        else:
            return False

    return True



def detect_mime_type(file_path: Path) -> str:
    mime, _ = mimetypes.guess_type(file_path.as_uri())
    return mime or "application/octet-stream"


def to_json(data: dict | list) -> str:
    return json.dumps(data, indent=2, default=str)
def resolve_ocr() -> object | None:
    global pytesseract
    if pytesseract is not None:
        return pytesseract
    try:
        import pytesseract as _pytesseract  # type: ignore[import]
    except ImportError:  # pragma: no cover - optional dependency
        return None
    pytesseract = _pytesseract
    return pytesseract
