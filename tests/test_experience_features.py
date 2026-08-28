from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app import item_rolling_summary, normalized_items
from bs_calendar import normalize_date_pair


def test_ad_date_is_normalized_to_bs():
    result = normalize_date_pair("2024-04-13", "ad")
    assert result["ad"] == "2024-04-13"
    assert result["bs"] == "2081-01-01"


def test_bs_date_round_trips_to_ad():
    result = normalize_date_pair("2081-01-01", "bs")
    assert result["ad"] == "2024-04-13"
    assert result["bs"] == "2081-01-01"


def test_rolling_summary_sums_same_item_in_overlapping_twelve_month_window():
    experiences = [
        SimpleNamespace(item_quantities=[{"item": "M20", "item_key": "m20", "unit": "m3", "quantity": "10", "from_ad": "2023-05-01", "till_ad": "2024-04-30"}]),
        SimpleNamespace(item_quantities=[{"item": "M20", "item_key": "m20", "unit": "m3", "quantity": "7", "from_ad": "2023-09-01", "till_ad": "2024-02-01"}]),
        SimpleNamespace(item_quantities=[{"item": "M20", "item_key": "m20", "unit": "m3", "quantity": "9", "from_ad": "2020-01-01", "till_ad": "2020-12-31"}]),
    ]
    result = item_rolling_summary(experiences)
    assert len(result) == 1
    assert result[0]["quantity"] == Decimal("17")
    assert result[0]["projects"] == 2


def test_rolling_summary_selects_highest_total_not_latest_window():
    experiences = [
        SimpleNamespace(item_quantities=[{"item": "M20", "item_key": "m20", "unit": "m3", "quantity": "100", "from_ad": "2023-05-01", "till_ad": "2024-04-30"}]),
        SimpleNamespace(item_quantities=[{"item": "M20", "item_key": "m20", "unit": "m3", "quantity": "80", "from_ad": "2023-09-01", "till_ad": "2024-02-01"}]),
        SimpleNamespace(item_quantities=[{"item": "M20", "item_key": "m20", "unit": "m3", "quantity": "5", "from_ad": "2025-01-01", "till_ad": "2025-12-31"}]),
    ]
    result = item_rolling_summary(experiences)
    assert len(result) == 1
    assert result[0]["quantity"] == Decimal("180")
    assert result[0]["projects"] == 2
    assert result[0]["till_ad"] == "2024-04-30"


def test_normalized_items_keeps_optional_dates_empty():
    form = SimpleNamespace(
        getlist=lambda name: {
            "item_name": ["TMT"],
            "item_unit": ["MT"],
            "item_quantity": ["12.5"],
            "item_from": [""],
            "item_till": [""],
        }[name]
    )
    assert normalized_items(form) == [{"item": "TMT", "item_key": "tmt", "unit": "MT", "quantity": "12.5"}]
