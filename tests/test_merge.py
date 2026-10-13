import pytest

from app.merge import merge_orders, normalize_phone, parse_amount


@pytest.mark.parametrize("raw, expected", [
    ("+7 999 123-45-67", "+79991234567"),
    ("8 (999) 123 45 67", "+79991234567"),
    ("79991234567", "+79991234567"),
    ("8-916-000-00-01", "+79160000001"),
    ("+7-926-123-45-67", "+79261234567"),
    ("9005551212", "+79005551212"),
    (79991234567, "+79991234567"),
    ("123", None),
    ("", None),
    ("не указан", None),
    ("+7 999", None),
    ("+1 999 123 45 67", None),
    ("8 999 123 45 67 доб. 12", None),
    (None, None),
    (True, None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    (5000, 5000), ("5000", 5000), ("1 500,50", 1500.5), (None, 0), ("abc", 0), ("NaN", 0), (2.0, 2),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def order(id, phone, amount, created_at, name="", email=""):
    return {"id": id, "name": name, "phone": phone, "email": email, "amount": amount, "created_at": created_at}


def test_max_amount_wins_regardless_of_order():
    orders = [
        order(1, "+7 999 123-45-67", 1000, "2026-10-01T10:00:00Z", "Иван Петров"),
        order(2, "8 (999) 123 45 67", 5000, "2026-10-02T11:00:00Z", "Иван П."),
        order(3, "79991234567", 3000, "2026-10-03T09:00:00Z", "И. Петров"),
    ]
    for sequence in (orders, orders[::-1]):
        result = merge_orders(sequence)
        assert [c.as_dict() for c in result.clients] == [
            {"name": "Иван П.", "phone": "+79991234567", "email": "", "amount": 5000},
        ]
        assert result.stats() == {"received": 3, "unique": 1, "duplicates_merged": 2, "invalid_dropped": 0}


def test_equal_amount_later_created_at_wins():
    orders = [
        order(5, "+7 (916) 000 00 01", 200, "2026-10-05T12:00:00Z", "Мария С."),
        order(4, "8-916-000-00-01", 200, "2026-10-01T12:00:00Z", "Мария Сидорова"),
    ]
    assert merge_orders(orders).clients[0].name == "Мария С."


def test_created_at_compared_as_moments_not_strings():
    orders = [
        order(1, "89990000000", 100, "2026-10-01T12:00:00+03:00", "раньше"),  # 09:00 UTC
        order(2, "89990000000", 100, "2026-10-01T10:00:00Z", "позже"),
    ]
    assert merge_orders(orders).clients[0].name == "позже"


def test_invalid_counted_and_dropped():
    orders = [order(1, "123", 999, ""), order(2, "", 1, ""), "мусор", order(3, "89990000000", 1, "")]
    result = merge_orders(orders)
    assert result.stats() == {"received": 4, "unique": 1, "duplicates_merged": 0, "invalid_dropped": 3}
