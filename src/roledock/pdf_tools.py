"""PDF parser limited to explicitly approved document IDs, never arbitrary paths."""
import fitz
from .models import RoleProfile
from .security import require_document, require_tool

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PAGES = 25


class ApprovedPdfRegistry:
    def __init__(self, approved_bytes: dict[str, bytes] | None = None):
        self._documents = dict(approved_bytes or {})

    def read(self, profile: RoleProfile, file_id: str) -> bytes:
        require_tool(profile, "parse_approved_pdf")
        require_document(profile, file_id)
        try:
            return self._documents[file_id]
        except KeyError as exc:
            raise FileNotFoundError("approved_document_not_registered") from exc


def parse_approved_pdf(profile: RoleProfile, file_id: str, registry: ApprovedPdfRegistry) -> str:
    raw = registry.read(profile, file_id)
    if len(raw) > MAX_PDF_BYTES:
        raise ValueError("pdf_size_limit")
    with fitz.open(stream=raw, filetype="pdf") as pdf:
        if pdf.page_count > MAX_PAGES:
            raise ValueError("pdf_page_limit")
        return "\n".join(page.get_text(sort=True) for page in pdf)


def synthetic_finance_pdf_registry() -> ApprovedPdfRegistry:
    """Explicitly generated fake finance policy for the localhost HITL demo.

    Not a document from ATM Capital or any real institution.
    """
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "RoleDock synthetic finance policy (demo only)")
        page.insert_text((72, 92), "Payment review needs two-person approval.")
        data = document.tobytes()
    return ApprovedPdfRegistry({"sample-finance-policy": data})
