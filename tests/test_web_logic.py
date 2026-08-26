from decimal import Decimal
from types import SimpleNamespace

from app import bid_data, financial_calculation


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
