"""Contract tests: pipeline result serialization and adapter error text."""

from __future__ import annotations

import json

from fastapi import HTTPException

from app.services.background_tasks import _PIPELINE_TASK_TYPES, background_task_service


def test_cidr_rollback_result_is_exposed():
    assert "cidr_rollback" in _PIPELINE_TASK_TYPES

    payload = {
        "task_id": "t-1",
        "task_type": "cidr_rollback",
        "status": "completed",
        "message": "Откат CIDR завершён",
        "output": json.dumps(
            {
                "success": True,
                "backup_stamp": "20260101-120000",
                "restored": ["cidr.txt"],
                "missing": [],
                "per_node": {"node-1": {"success": True}},
            },
            ensure_ascii=False,
        ),
        "error": None,
    }
    result = background_task_service.serialize_background_task(payload)["result"]

    assert isinstance(result, dict)
    assert result["backup_stamp"] == "20260101-120000"
    assert result["per_node"] == {"node-1": {"success": True}}


def test_adapter_error_unwraps_link_error_dict():
    exc = HTTPException(
        status_code=502,
        detail={
            "code": "node_unreachable",
            "message": "Узел недоступен",
            "hint": "Проверьте SSH",
        },
    )
    text = str(background_task_service._adapter_error(exc))

    assert "Узел недоступен" in text
    assert "Проверьте SSH" in text
    assert "{" not in text
    assert "'code'" not in text
    assert "node_unreachable" not in text


def test_adapter_error_keeps_string_detail():
    exc = HTTPException(status_code=400, detail="Некорректный запрос агента")
    assert str(background_task_service._adapter_error(exc)) == "Некорректный запрос агента"


def test_adapter_error_keeps_plain_exceptions():
    class _AdapterFailure(Exception):
        pass

    assert str(background_task_service._adapter_error(ValueError("boom"))) == "boom"
    assert str(background_task_service._adapter_error(_AdapterFailure("down"))) == "down"


def test_adapter_error_serializes_unknown_dict_as_json():
    exc = HTTPException(status_code=400, detail={"field": "backup_stamp"})
    text = str(background_task_service._adapter_error(exc))
    assert json.loads(text) == {"field": "backup_stamp"}
