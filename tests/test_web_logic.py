from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from docx import Document

from app import bid_data, financial_calculation
from doc_generator import build_exp1_doc, build_fin2_doc


def test_financial_calculation_selects_best_three_of_latest_five():
    rows = [
        SimpleNamespace(fiscal_year=year, turnover_amount=Decimal(amount), jv_entries=[])
        for year, amount in (("2077/078", "100"), ("2078/079", "500"), ("2079/080", "200"), ("2080/081", "400"), ("2081/082", "300"), ("2082/083", "900"))
    ]
    indices = [SimpleNamespace(fiscal_year=year, index_value=Decimal("100")) for year in ("2077/078", "2078/079", "2079/080", "2080/081", "2081/082", "2082/083")]
    result = financial_calculation(rows, indices)
    assert [item["year"] for item in result["selected"]] == ["2082/083", "2078/079", "2080/081"]
    assert result["average"] == Decimal("600")


def test_single_bidder_normalizes_jv_and_share():
    data = bid_data({
        "BID_TYPE": "Single Bidder",
        "LEAD_PARTNER_NAME": "Lead Builders",
        "LEAD_ADDRESS": "Kathmandu",
        "L_PER": "100.00",
    })
    assert data["JV_NAME"] == "Lead Builders"
    assert data["JV_ADDRESS"] == "Kathmandu"
    assert data["L_PER"] == "100%"
    assert data["AND_CONNECTOR"] == ""


def test_fin2_total_includes_jv_and_present_value_uses_corrected_total():
    entry = SimpleNamespace(fiscal_year="2080/081", turnover_amount=Decimal("41250006.00"), jv_entries=[SimpleNamespace(attributed_amount=Decimal("10389925.20"), share_percentage=Decimal("25"), jv_name="JV Co", jv_address="Kathmandu", vat_number="VAT-1")])
    content = build_fin2_doc("Example Builders", [entry], {"2080/081": Decimal("100")}, Decimal("100"), [("2080/081", "51,639,931.20")], Decimal("51639931.20"))
    table = Document(BytesIO(content)).tables[0]
    assert table.rows[1].cells[3].text == "51,639,931.20"
    assert table.rows[1].cells[6].text == "51,639,931.20"


def test_exp1_year_column_uses_completion_year():
    entry = SimpleNamespace(start_month_year="Jan 2078", end_month_year="Dec 2080", completion_date="2080-12-30", contract_id="C-1", contract_name="Bridge", employer_name="Road Office", employer_address="Pokhara", work_description="Bridge construction", role="Contractor")
    table = Document(BytesIO(build_exp1_doc("Example Builders", [entry]))).tables[0]
    assert [cell.text for cell in table.rows[0].cells[:3]] == ["Starting month/year", "Ending month/year", "Year"]
    assert table.rows[1].cells[2].text == "2080"
