from __future__ import annotations

from gdis_loader.config import CriteriaConfig
from gdis_loader.domain.models import DatePrecision, PartialDate
from gdis_loader.transforms.aggregates import (
    GdiCountBounds,
    chlorine_growth,
    insufficient_gdi_from_bounds,
    mean_working_day_rate,
    productivity_decline,
)
from gdis_loader.transforms.research_status import gdm_problem
from gdis_loader.transforms.rules import downhole_condition


def test_each_criteria_value_changes_its_business_result() -> None:
    two_gdi = GdiCountBounds(2, 2, (), ())
    assert not insufficient_gdi_from_bounds(two_gdi, CriteriaConfig().insufficient_gdi_min_count)
    assert insufficient_gdi_from_bounds(
        two_gdi, CriteriaConfig(insufficient_gdi_min_count=3).insufficient_gdi_min_count
    )

    assert productivity_decline(1.0, 1.1, CriteriaConfig().productivity_min_increase)
    assert not productivity_decline(
        1.0, 1.1, CriteriaConfig(productivity_min_increase=0.11).productivity_min_increase
    )

    chlorine_default = CriteriaConfig()
    assert chlorine_growth(
        2501.0,
        1000.0,
        chlorine_default.chlorine_current_min_mg_dm3,
        chlorine_default.chlorine_delta_min_mg_dm3,
    )
    current_threshold = CriteriaConfig(chlorine_current_min_mg_dm3=2501.0)
    assert not chlorine_growth(
        2501.0,
        1000.0,
        current_threshold.chlorine_current_min_mg_dm3,
        current_threshold.chlorine_delta_min_mg_dm3,
    )
    delta_threshold = CriteriaConfig(chlorine_delta_min_mg_dm3=1501.0)
    assert not chlorine_growth(
        2501.0,
        1000.0,
        delta_threshold.chlorine_current_min_mg_dm3,
        delta_threshold.chlorine_delta_min_mg_dm3,
    )

    assert downhole_condition(500.0, CriteriaConfig().downhole_depth_threshold_m)
    assert not downhole_condition(
        500.0, CriteriaConfig(downhole_depth_threshold_m=1000.0).downhole_depth_threshold_m
    )

    assert gdm_problem(6.0, CriteriaConfig().gdm_abs_delta_threshold)
    assert not gdm_problem(6.0, CriteriaConfig(gdm_abs_delta_threshold=7.0).gdm_abs_delta_threshold)

    values = (10.0, 100.0, 120.0)
    assert mean_working_day_rate(values, CriteriaConfig()) == 230.0 / 3
    assert (
        mean_working_day_rate(values, CriteriaConfig(gas_rate_working_day_min_rate=100.0)) == 120.0
    )


def test_year_defaulting_is_injected_as_effective_calendar_date() -> None:
    launch = PartialDate(2024, None, None, DatePrecision.YEAR)

    assert launch.year == 2024
    assert CriteriaConfig().gdm_fallback_max_age_days == 365
