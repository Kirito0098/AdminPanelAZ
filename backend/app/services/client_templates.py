"""Client template CRUD and apply (one-click create)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ClientTemplate, User, UserRole, VpnConfig, VpnType
from app.services.access_policy import AccessPolicyService
from app.services.feature_guards import FeatureToggleService, require_vpn_type
from app.services.node_manager import get_active_adapter, get_active_node, get_node_antizapret_path
from app.services.traffic_limit import parse_traffic_limit_bytes


def list_templates(db: Session, node_id: int) -> list[ClientTemplate]:
    return (
        db.query(ClientTemplate)
        .filter(ClientTemplate.node_id == node_id)
        .order_by(ClientTemplate.sort_order.asc(), ClientTemplate.name.asc())
        .all()
    )


def get_template(db: Session, node_id: int, template_id: int) -> ClientTemplate | None:
    return (
        db.query(ClientTemplate)
        .filter(ClientTemplate.node_id == node_id, ClientTemplate.id == template_id)
        .first()
    )


def create_template(db: Session, node_id: int, **fields) -> ClientTemplate:
    name = str(fields.get("name") or "").strip()
    conflict = (
        db.query(ClientTemplate)
        .filter(ClientTemplate.node_id == node_id, ClientTemplate.name == name)
        .first()
    )
    if conflict:
        raise ValueError("Шаблон с таким именем уже существует")
    row = ClientTemplate(node_id=node_id, is_builtin=False, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_template(db: Session, template: ClientTemplate, **fields) -> ClientTemplate:
    if "name" in fields and fields["name"] is not None:
        name = str(fields["name"]).strip()
        conflict = (
            db.query(ClientTemplate)
            .filter(
                ClientTemplate.node_id == template.node_id,
                ClientTemplate.name == name,
                ClientTemplate.id != template.id,
            )
            .first()
        )
        if conflict:
            raise ValueError("Шаблон с таким именем уже существует")
        template.name = name
        del fields["name"]
    for key, value in fields.items():
        if value is not None or key in ("description_template", "traffic_limit_value", "traffic_limit_unit"):
            setattr(template, key, value)
    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template: ClientTemplate) -> None:
    if template.is_builtin:
        raise ValueError("Встроенный шаблон нельзя удалить")
    db.delete(template)
    db.commit()


def apply_template(
    db: Session,
    template: ClientTemplate,
    *,
    client_name: str,
    owner_id: int,
    actor: User,
    feature_service: FeatureToggleService,
) -> VpnConfig:
    require_vpn_type(template.vpn_type.value, service=feature_service)

    node = get_active_node(db)
    if template.node_id != node.id:
        raise ValueError("Шаблон принадлежит другому узлу")

    existing = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node.id,
            VpnConfig.client_name == client_name,
            VpnConfig.vpn_type == template.vpn_type,
        )
        .first()
    )
    if existing:
        raise ValueError("Конфигурация уже существует")

    owner = db.query(User).filter(User.id == owner_id).first()
    if not owner:
        raise ValueError("Владелец не найден")
    if actor.role != UserRole.admin and owner_id != actor.id:
        raise ValueError("Недостаточно прав для назначения владельца")

    adapter = get_active_adapter(db)
    cert_days = template.cert_expire_days or 3650
    if template.vpn_type == VpnType.openvpn:
        adapter.add_openvpn_client(client_name, cert_days)
    else:
        adapter.add_wireguard_client(client_name)

    config = VpnConfig(
        node_id=node.id,
        client_name=client_name,
        vpn_type=template.vpn_type,
        owner_id=owner_id,
        cert_expire_days=cert_days if template.vpn_type == VpnType.openvpn else None,
        description=template.description_template,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    if template.traffic_limit_value and template.traffic_limit_unit:
        limit_bytes = parse_traffic_limit_bytes(
            template.traffic_limit_value,
            template.traffic_limit_unit,
        )
        svc = AccessPolicyService(
            db,
            antizapret_path=get_node_antizapret_path(db),
            node_id=node.id,
            adapter=adapter,
        )
        if template.vpn_type == VpnType.openvpn:
            svc.openvpn_set_traffic_limit(
                client_name,
                limit_bytes,
                period_days=template.traffic_limit_period_days,
                actor=actor.username,
            )
        else:
            svc.wg_set_traffic_limit(
                client_name,
                limit_bytes,
                period_days=template.traffic_limit_period_days,
                actor=actor.username,
            )

    return config
