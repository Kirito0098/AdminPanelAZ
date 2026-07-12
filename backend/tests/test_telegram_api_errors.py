from app.services.telegram_api import format_telegram_connect_error


def test_network_unreachable_message():
    msg = format_telegram_connect_error(
        "[Errno 101] Network is unreachable",
        operation="подключить бота к панели",
    )
    assert "Не удалось подключить бота к панели" in msg
    assert "api.telegram.org" in msg
    assert "исходящий запрос" in msg
    assert "curl -4 https://api.telegram.org/" in msg
    assert "Network is unreachable" in msg


def test_timeout_message():
    msg = format_telegram_connect_error(
        "timed out",
        operation="подключить бота к панели",
    )
    assert "истекло время ожидания" in msg


def test_https_required_from_telegram():
    msg = format_telegram_connect_error(
        "Bad Request: HTTPS URL must be provided",
        operation="подключить бота к панели",
    )
    assert "только по HTTPS" in msg


def test_unknown_error_fallback():
    msg = format_telegram_connect_error(
        "Something odd",
        operation="настроить команды бота",
    )
    assert msg == "Не удалось настроить команды бота: Something odd"
