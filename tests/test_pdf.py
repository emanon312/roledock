import fitz
from roledock.pdf_tools import ApprovedPdfRegistry
from roledock.runtime import RoleDock


def make_pdf():
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((70, 70), "Approved Finance Policy Demo")
    data = pdf.tobytes()
    pdf.close()
    return data


def test_finance_preapproved_pdf_can_parse(principals):
    registry = ApprovedPdfRegistry({"sample-finance-policy": make_pdf()})
    result = RoleDock(pdf_registry=registry).execute(
        principals["finance"], "解析PDF", "sample-finance-policy")
    assert result.status == "completed"
    assert "Approved Finance Policy Demo" in result.content


def test_approved_id_but_missing_registration_fails(principals):
    result = RoleDock().execute(principals["finance"], "解析PDF", "sample-finance-policy")
    assert result.status == "failed"
