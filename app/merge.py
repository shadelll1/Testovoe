"""Нормализация телефонов и схлопывание дублей. Чистые функции, без сети и базы."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

_EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


def normalize_phone(raw) -> str | None:
    """Приводит телефон к виду +7XXXXXXXXXX или возвращает None, если номер невалиден.

    Из строки берутся только цифры:
    - 11 цифр, первая 7 или 8 («+7 999…», «8 (999)…») — код страны заменяется на 7;
    - 10 цифр («999 123-45-67») — номер без кода страны, дописывается 7;
    - всё остальное (пусто, текст, обрезанный номер, чужой код страны) — невалидно.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        raw = str(raw)
    if not isinstance(raw, str):
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return None


def parse_amount(raw) -> int | float:
    """Сумма заявки числом. Строку «5000» понимает, мусор и пустое значение считает нулём."""
    if isinstance(raw, bool) or raw is None:
        return 0
    try:
        value = Decimal(str(raw).strip().replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return 0
    if not value.is_finite():
        return 0
    return int(value) if value == value.to_integral_value() else float(value)


def parse_created_at(raw) -> datetime:
    """Момент заявки для сравнения. Без часового пояса считаем UTC; нечитаемая дата — самая ранняя."""
    if not isinstance(raw, str) or not raw.strip():
        return _EARLIEST
    try:
        moment = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return _EARLIEST
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _text(raw) -> str:
    return raw.strip() if isinstance(raw, str) else ""


@dataclass(frozen=True)
class Client:
    name: str
    phone: str
    email: str
    amount: int | float
    position: int  # порядок первого появления телефона в источнике — для стабильного вывода

    def as_dict(self) -> dict:
        return {"name": self.name, "phone": self.phone, "email": self.email, "amount": self.amount}


@dataclass(frozen=True)
class MergeResult:
    clients: list[Client]
    received: int
    invalid_dropped: int

    @property
    def unique(self) -> int:
        return len(self.clients)

    @property
    def duplicates_merged(self) -> int:
        return self.received - self.invalid_dropped - self.unique

    def stats(self) -> dict:
        return {
            "received": self.received,
            "unique": self.unique,
            "duplicates_merged": self.duplicates_merged,
            "invalid_dropped": self.invalid_dropped,
        }


def merge_orders(orders: list) -> MergeResult:
    """Нормализует заявки и оставляет по одной на телефон.

    Из дублей выигрывает заявка с наибольшей суммой, при равной сумме — более поздняя по created_at.
    Если совпало и то и другое, берётся встреченная позже в выдаче — так результат всегда однозначен.
    Элемент, который не объект, считается заявкой с невалидным телефоном.
    """
    best: dict[str, tuple[tuple, Client]] = {}
    invalid = 0
    for index, order in enumerate(orders):
        phone = normalize_phone(order.get("phone")) if isinstance(order, dict) else None
        if phone is None:
            invalid += 1
            continue
        amount = parse_amount(order.get("amount"))
        key = (amount, parse_created_at(order.get("created_at")), index)
        position = best[phone][1].position if phone in best else index
        if phone not in best or key > best[phone][0]:
            best[phone] = (key, Client(
                name=_text(order.get("name")),
                phone=phone,
                email=_text(order.get("email")),
                amount=amount,
                position=position,
            ))
    clients = sorted((client for _, client in best.values()), key=lambda c: c.position)
    return MergeResult(clients=clients, received=len(orders), invalid_dropped=invalid)
