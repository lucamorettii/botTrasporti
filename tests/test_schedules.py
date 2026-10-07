from datetime import date

from src.bottrasporti.schedules import get_prossimo_bus


def test_returns_run_for_matching_weekday():
    departure, arrival = get_prossimo_bus(
        "data/bus_brusa_bg.csv",
        "06:00",
        date(2026, 10, 5),  # Monday
    )

    assert (departure, arrival) == ("06:42", "07:00")


def test_skips_weekday_only_run_on_saturday():
    departure, arrival = get_prossimo_bus(
        "data/bus_brusa_bg.csv",
        "08:20",
        date(2026, 10, 10),  # Saturday
    )

    assert (departure, arrival) == ("08:27", "08:45")


def test_returns_bergamo_albano_run():
    departure, arrival = get_prossimo_bus(
        "data/bus_bg_albano.csv",
        "17:00",
        date(2026, 10, 5),  # Monday
    )

    assert (departure, arrival) == ("17:05", "17:21")
