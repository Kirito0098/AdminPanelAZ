from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import AlertRule, AlertRuleMetric, AlertRuleOperator, Node, User
from app.schemas import (
    AlertMetricInfo,
    AlertRuleCreate,
    AlertRuleEvaluateResponse,
    AlertRuleResponse,
    AlertRuleUpdate,
    MessageResponse,
)
from app.services.alert_rules import (
    METRICS_REQUIRING_NODE,
    evaluate_alert_rules,
    metric_catalog,
)

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


def _to_response(rule: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse.model_validate(rule)


def _parse_metric(value: str | AlertRuleMetric) -> AlertRuleMetric:
    if isinstance(value, AlertRuleMetric):
        return value
    try:
        return AlertRuleMetric(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестная метрика") from exc


def _parse_operator(value: str | AlertRuleOperator) -> AlertRuleOperator:
    if isinstance(value, AlertRuleOperator):
        return value
    try:
        return AlertRuleOperator(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный оператор") from exc


def _validate_rule_payload(
    *,
    metric: AlertRuleMetric,
    node_id: int | None,
    db: Session,
) -> None:
    metric_key = metric.value if hasattr(metric, "value") else str(metric)
    if metric_key in METRICS_REQUIRING_NODE and node_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Для этой метрики нужно указать узел",
        )
    if node_id is not None:
        node = db.query(Node).filter(Node.id == node_id).first()
        if not node:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Узел не найден")


@router.get("/metrics", response_model=list[AlertMetricInfo])
def list_alert_metrics(_: User = Depends(require_admin)):
    return [AlertMetricInfo.model_validate(item) for item in metric_catalog()]


@router.get("", response_model=list[AlertRuleResponse])
def list_alert_rules(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rules = db.query(AlertRule).order_by(AlertRule.id.asc()).all()
    return [_to_response(rule) for rule in rules]


@router.post("", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    metric = _parse_metric(payload.metric)
    _validate_rule_payload(metric=metric, node_id=payload.node_id, db=db)
    rule = AlertRule(
        name=payload.name,
        metric=metric,
        operator=_parse_operator(payload.operator),
        threshold=payload.threshold,
        node_id=payload.node_id,
        cooldown_minutes=payload.cooldown_minutes,
        enabled=payload.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _to_response(rule)


@router.patch("/{rule_id}", response_model=AlertRuleResponse)
def update_alert_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Правило не найдено")

    data = payload.model_dump(exclude_none=True)
    metric = _parse_metric(data.get("metric", rule.metric))
    node_id = data.get("node_id", rule.node_id)
    _validate_rule_payload(metric=metric, node_id=node_id, db=db)
    if "metric" in data:
        data["metric"] = metric
    if "operator" in data:
        data["operator"] = _parse_operator(data["operator"])

    for key, value in data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return _to_response(rule)


@router.delete("/{rule_id}", response_model=MessageResponse)
def delete_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Правило не найдено")
    db.delete(rule)
    db.commit()
    return MessageResponse(message="Правило удалено")


@router.post("/evaluate", response_model=AlertRuleEvaluateResponse)
def evaluate_alert_rules_now(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    results = evaluate_alert_rules(db, notify=True)
    triggered = sum(1 for item in results if item.get("triggered"))
    return AlertRuleEvaluateResponse(evaluated=len(results), triggered=triggered, results=results)
