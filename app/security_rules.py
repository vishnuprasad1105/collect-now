from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChecklistRule:
    id: str
    label: str
    keywords_all: tuple[str, ...]
    category: str = "checklist"
    require_yes: bool = False
    hint: str | None = None


@dataclass(frozen=True)
class TextExpectation:
    id: str
    label: str
    keywords_all: tuple[str, ...] = ()
    keywords_any: tuple[str, ...] = ()
    category: str = "validation"
    hint: str | None = None


@dataclass(frozen=True)
class FieldBundle:
    id: str
    label: str
    fields: tuple[str, ...]
    category: str
    hint: str


@dataclass(frozen=True)
class ImageTextExpectation:
    id: str
    label: str
    description: str
    keywords_all: tuple[str, ...] = ()
    keywords_any: tuple[str, ...] = ()
    threshold_all: int = 80
    threshold_any: int = 80
    apply_document_fallback: bool = False
    category: str = "visual"
    hint: str | None = None


BASE_CHECKLIST_RULES: tuple[ChecklistRule, ...] = (
    ChecklistRule(
        id="check_01_database",
        label="1) Maintain database to store the transaction details / status (YES)",
        keywords_all=("maintain", "database", "transaction", "status"),
        require_yes=True,
        hint="Confirm the checklist explicitly documents database retention with a YES acknowledgement.",
    ),
    ChecklistRule(
        id="check_02_payment_confirmation",
        label=(
            "2) Services / payment confirmation to customer / user provided on basis of database status (YES)"
        ),
        keywords_all=("payment", "confirmation", "database", "status"),
        require_yes=True,
        hint="Validate customer confirmation derives from database status and is marked YES.",
    ),
    ChecklistRule(
        id="check_03_audit_transactions",
        label="3) 7-8 transactions performed in the Security Audit process (YES)",
        keywords_all=("7-8", "transactions", "security", "audit"),
        require_yes=True,
    ),
    ChecklistRule(
        id="check_04_login_credentials",
        label="4) Login credentials available till audit completion (YES)",
        keywords_all=("login", "credentials", "audit", "completion"),
        require_yes=True,
    ),
    ChecklistRule(
        id="check_05_no_purge",
        label="5) Database records not cleared till audit completion (YES)",
        keywords_all=("do", "not", "clear", "database", "records"),
        require_yes=True,
    ),
    ChecklistRule(
        id="check_06_uat_parity",
        label="6) Provided UAT setup identical to production setup (YES)",
        keywords_all=("uat", "identical", "production", "setup"),
        require_yes=True,
    ),
    ChecklistRule(
        id="check_07_dual_inquiry",
        label="7) Dual inquiry Status API implemented in response (YES)",
        keywords_all=("dual", "inquiry", "status", "api"),
        require_yes=True,
    ),
    ChecklistRule(
        id="check_08_audit_checklist",
        label="8) Audit checklist implemented for integration & security audit (YES)",
        keywords_all=("audit", "checklist", "integration", "security"),
        require_yes=True,
    ),
)


ADDITIONAL_TEXT_EXPECTATIONS: tuple[TextExpectation, ...] = (
    TextExpectation(
        id="brand_hdfc_collectnow",
        label="Document references HDFC CollectNow branding",
        keywords_all=("hdfc", "collect", "now"),
        category="branding",
        hint="Ensure the document explicitly mentions HDFC CollectNow branding.",
    ),
    TextExpectation(
        id="brand_color_palette",
        label="Brand color palette mentioned (blue & red)",
        keywords_any=("blue", "navy"),
        keywords_all=("red",),
        category="branding",
        hint="Look for narrative confirming the red/blue brand palette.",
    ),
    TextExpectation(
        id="api_checkout_embedded",
        label="Checkout embed URL documented",
        keywords_all=("api.razorpay.com/v1/checkout/embedded",),
        category="api",
        hint="URL must appear exactly as api.razorpay.com/v1/checkout/embedded.",
    ),
    TextExpectation(
        id="api_status_endpoint",
        label="Status API endpoint referenced",
        keywords_any=("/v1/status", "status api"),
        keywords_all=("api",),
        category="api",
    ),
    TextExpectation(
        id="screenshot_payment_success",
        label="Payment success scenario documented",
        keywords_any=("payment success", "transaction success", "success status"),
        category="screenshots",
    ),
    TextExpectation(
        id="screenshot_payment_failure",
        label="Payment failure scenario documented",
        keywords_any=("payment failure", "transaction failure", "failed status"),
        category="screenshots",
    ),
)


REQUEST_REQUIRED_FIELDS = FieldBundle(
    id="request_payload",
    label="Request payload includes mandatory parameters",
    fields=(
        "merchant_id",
        "order_id",
        "amount",
        "currency",
        "payment_capture",
        "callback_url",
        "customer_id",
        "customer_email",
    ),
    category="api-contract",
    hint="Confirm sample requests in the document include the mandatory Razorpay CollectNow parameters.",
)


RESPONSE_REQUIRED_FIELDS = FieldBundle(
    id="response_payload",
    label="Response payload includes mandatory parameters",
    fields=(
        "payment_id",
        "order_id",
        "status",
        "signature",
        "amount",
        "currency",
        "acquirer_data",
        "method",
    ),
    category="api-contract",
    hint="Confirm sample responses list identifiers, status, and signature for verification.",
)


IMAGE_TEXT_EXPECTATIONS: tuple[ImageTextExpectation, ...] = (
    ImageTextExpectation(
        id="visual_logo",
        label="HDFC SmartCollect branding visible",
        description="Screenshots include the HDFC SmartCollect or CollectNow branding.",
        keywords_any=("hdfc smartcollect", "smart collect", "collectnow", "collect now"),
        threshold_any=70,
        hint="Ensure the UI captures the CollectNow logo or wording in uploaded evidence.",
    ),
    ImageTextExpectation(
        id="visual_checkout_url",
        label="Checkout embed URL displayed",
        description="Screenshots show the Razorpay checkout embed URL.",
        keywords_all=("api.razorpay.com",),
        keywords_any=("/v1/checkout/embedded", "checkout embedded", "checkout/embedded"),
        threshold_all=60,
        threshold_any=60,
        hint="Capture the browser bar that includes api.razorpay.com/v1/checkout/embedded.",
    ),
    ImageTextExpectation(
        id="visual_payment_success",
        label="Payment success screen present",
        description="Screenshots contain wording indicating a successful payment.",
        keywords_any=(
            "payment success",
            "payment successful",
            "transaction success",
            "payment completed",
            "success status",
            "successful payment",
            "payment processed successfully",
        ),
        threshold_any=70,
        hint="Include confirmation screens that clearly proclaim a successful transaction.",
    ),
    ImageTextExpectation(
        id="visual_payment_failure",
        label="Payment failure screen present",
        description="Screenshots contain wording indicating a failed payment.",
        keywords_any=(
            "payment failure",
            "payment failed",
            "transaction failed",
            "failure status",
            "error processing payment",
            "payment could not be processed",
        ),
        threshold_any=70,
        hint="Include failure experience evidence with explicit failure strings.",
    ),
)
