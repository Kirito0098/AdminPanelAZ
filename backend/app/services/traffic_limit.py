"""Helpers for traffic-based client access limits (ported from AdminAntizapret 1.9.0)."""

from datetime import datetime, timedelta, timezone

TRAFFIC_LIMIT_EXCEEDED_MESSAGE = (
    "Клиент отключён по превышению лимита трафика. "
    "Для разблокировки увеличьте лимит, снимите его или очистите статистику трафика."
)
TRAFFIC_LIMIT_EXCEEDED_CODE = "traffic_limit_exceeded"

TRAFFIC_LIMIT_UNITS = {
    "b": 1,
    "kb": 1024,
    "mb": 1024**2,
    "gb": 1024**3,
    "tb": 1024**4,
}

TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED = (1, 7, 30)


class TrafficLimitExceededError(ValueError):
    error_code = TRAFFIC_LIMIT_EXCEEDED_CODE

    def __init__(self, message=TRAFFIC_LIMIT_EXCEEDED_MESSAGE):
        super().__init__(message)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_traffic_limit_unit(unit: str | None) -> str:
    normalized = (unit or "mb").strip().lower()
    if normalized in ("byte", "bytes"):
        return "b"
    return normalized


def parse_traffic_limit_bytes(value, unit="mb") -> int:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректное значение лимита трафика.") from exc

    if amount <= 0:
        raise ValueError("Лимит трафика должен быть больше 0.")

    normalized_unit = normalize_traffic_limit_unit(unit)
    multiplier = TRAFFIC_LIMIT_UNITS.get(normalized_unit)
    if multiplier is None:
        raise ValueError("Единица лимита трафика должна быть одной из: B, KB, MB, GB, TB.")

    limit_bytes = int(amount * multiplier)
    if limit_bytes < 1:
        raise ValueError("Лимит трафика должен быть не меньше 1 байта.")
    return limit_bytes


def parse_traffic_limit_period_days(value) -> int | None:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    try:
        period_days = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Период лимита трафика должен быть 1, 7 или 30 дней.") from exc

    if period_days not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        raise ValueError("Период лимита трафика должен быть 1, 7 или 30 дней.")
    return period_days


def format_traffic_limit_period_label(period_days: int | None) -> str:
    if period_days == 1:
        return "за сутки (календарный день)"
    if period_days == 7:
        return "за неделю (пн–вс)"
    if period_days == 30:
        return "за месяц"
    if period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        return f"{period_days} дн."
    if period_days is None:
        return "всё время"
    return f"{period_days} дн."


def get_traffic_limit_period_bounds(period_days: int, now=None):
    if period_days not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        return None, None

    now = _as_utc(now) or datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period_days == 1:
        return day_start, day_start + timedelta(days=1)

    if period_days == 7:
        week_start = day_start - timedelta(days=now.weekday())
        return week_start, week_start + timedelta(days=7)

    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)
    return month_start, month_end


def get_traffic_limit_period_unblock_at(period_days: int, now=None):
    _period_start, period_end = get_traffic_limit_period_bounds(period_days, now=now)
    return period_end


_WEEKDAY_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def format_traffic_limit_unblock_at(period_days: int | None, now=None):
    if period_days not in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        return None, None

    unblock_at = get_traffic_limit_period_unblock_at(period_days, now=now)
    if unblock_at is None:
        return None, None

    formatted_at = unblock_at.strftime("%Y-%m-%d %H:%M:%S")
    display_date = unblock_at.strftime("%d.%m.%Y")
    display_time = unblock_at.strftime("%H:%M")

    if period_days == 1:
        label = f"Авторазблокировка: {display_date} {display_time} UTC"
    elif period_days == 7:
        weekday = _WEEKDAY_RU[unblock_at.weekday()]
        label = f"Авторазблокировка: {display_date} {display_time} UTC ({weekday})"
    else:
        label = f"Авторазблокировка: {display_date} {display_time} UTC"

    return formatted_at, label


def human_bytes(value: int | None) -> str | None:
    if value is None:
        return None
    amount = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while amount >= 1024 and idx < len(units) - 1:
        amount /= 1024
        idx += 1
    if idx == 0:
        return f"{int(amount)} {units[idx]}"
    return f"{amount:.1f} {units[idx]}"


def resolve_traffic_limit_state(*, traffic_limit_bytes, traffic_limit_period_days=None, consumed_bytes):
    limit = int(traffic_limit_bytes) if traffic_limit_bytes is not None else None
    consumed = max(int(consumed_bytes or 0), 0)
    period_days = (
        int(traffic_limit_period_days)
        if traffic_limit_period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED
        else None
    )
    if limit is None or limit < 1:
        return {
            "traffic_limit_bytes": None,
            "traffic_limit_period_days": None,
            "traffic_limit_period_label": None,
            "traffic_limit_unblock_at": None,
            "traffic_limit_unblock_label": None,
            "traffic_consumed_bytes": consumed,
            "traffic_bytes_left": None,
            "traffic_limit_exceeded": False,
            "traffic_limit_human": None,
        }

    exceeded = consumed >= limit
    unblock_at, unblock_label = (
        format_traffic_limit_unblock_at(period_days) if period_days else (None, None)
    )
    return {
        "traffic_limit_bytes": limit,
        "traffic_limit_period_days": period_days,
        "traffic_limit_period_label": format_traffic_limit_period_label(period_days),
        "traffic_limit_unblock_at": unblock_at,
        "traffic_limit_unblock_label": unblock_label,
        "traffic_consumed_bytes": consumed,
        "traffic_bytes_left": 0 if exceeded else max(limit - consumed, 0),
        "traffic_limit_exceeded": exceeded,
        "traffic_limit_human": human_bytes(limit),
    }


def get_client_consumed_traffic_bytes(
    db,
    *,
    client_name: str,
    node_id: int | None = None,
    period_days: int | None = None,
    normalize_identity=None,
):
    from app.models import UserTrafficSample, UserTrafficStatProtocol

    normalize_identity = normalize_identity or (lambda name: (name or "").strip().lower())
    target = normalize_identity(client_name)
    if not target:
        return 0

    def _match_names(model):
        names = []
        query = db.query(model.common_name).distinct()
        if node_id is not None:
            query = query.filter(model.node_id == node_id)
        for (stored_name,) in query.all():
            candidate = (stored_name or "").strip()
            if candidate and normalize_identity(candidate) == target:
                names.append(candidate)
        return names

    if period_days in TRAFFIC_LIMIT_PERIOD_DAYS_ALLOWED:
        matched = _match_names(UserTrafficSample)
        if not matched:
            return 0
        now = datetime.now(timezone.utc)
        period_start, period_end = get_traffic_limit_period_bounds(period_days, now=now)
        since_dt = _as_utc(period_start).replace(tzinfo=None)
        until_dt = _as_utc(period_end).replace(tzinfo=None)
        query = db.query(UserTrafficSample).filter(
            UserTrafficSample.common_name.in_(matched),
            UserTrafficSample.created_at >= since_dt,
            UserTrafficSample.created_at < until_dt,
        )
        if node_id is not None:
            query = query.filter(UserTrafficSample.node_id == node_id)
        total = 0
        for row in query.all():
            total += int(row.delta_received or 0) + int(row.delta_sent or 0)
        return total

    matched = _match_names(UserTrafficStatProtocol)
    if not matched:
        return 0

    total = 0
    for candidate in matched:
        query = db.query(UserTrafficStatProtocol).filter_by(common_name=candidate)
        if node_id is not None:
            query = query.filter(UserTrafficStatProtocol.node_id == node_id)
        for row in query.all():
            total += int(row.total_received or 0) + int(row.total_sent or 0)
    return total
