import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"
    viewer = "viewer"


class VpnType(str, enum.Enum):
    openvpn = "openvpn"
    wireguard = "wireguard"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user)
    theme: Mapped[str] = mapped_column(String(16), default="dark")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    vpn_configs: Mapped[list["VpnConfig"]] = relationship(back_populates="owner")


class VpnConfig(Base):
    __tablename__ = "vpn_configs"
    __table_args__ = (UniqueConstraint("client_name", "vpn_type", name="uq_client_vpn_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_name: Mapped[str] = mapped_column(String(32), index=True)
    vpn_type: Mapped[VpnType] = mapped_column(Enum(VpnType))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    cert_expire_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner: Mapped["User"] = relationship(back_populates="vpn_configs")


class NodeStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    unknown = "unknown"


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=9100)
    api_key_hash: Mapped[str] = mapped_column(String(255), default="")
    api_key_encrypted: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[NodeStatus] = mapped_column(Enum(NodeStatus), default=NodeStatus.unknown)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False)
    node_metadata: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")


class TrafficSessionState(Base):
    __tablename__ = "traffic_session_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    session_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    profile: Mapped[str] = mapped_column(String(64), default="unknown")
    common_name: Mapped[str] = mapped_column(String(128), index=True)
    real_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    virtual_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connected_since_ts: Mapped[int] = mapped_column(Integer, default=0)
    last_bytes_received: Mapped[int] = mapped_column(Integer, default=0)
    last_bytes_sent: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserTrafficStatProtocol(Base):
    __tablename__ = "user_traffic_stat_protocol"
    __table_args__ = (UniqueConstraint("node_id", "common_name", "protocol_type", name="uq_traffic_node_client_proto"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    common_name: Mapped[str] = mapped_column(String(128), index=True)
    protocol_type: Mapped[str] = mapped_column(String(16), default="openvpn")
    total_received: Mapped[int] = mapped_column(Integer, default=0)
    total_sent: Mapped[int] = mapped_column(Integer, default=0)
    total_received_vpn: Mapped[int] = mapped_column(Integer, default=0)
    total_sent_vpn: Mapped[int] = mapped_column(Integer, default=0)
    total_received_antizapret: Mapped[int] = mapped_column(Integer, default=0)
    total_sent_antizapret: Mapped[int] = mapped_column(Integer, default=0)
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WgAccessPolicy(Base):
    __tablename__ = "wg_access_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_temp_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_permanent_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    block_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    block_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    block_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OpenVpnAccessPolicy(Base):
    __tablename__ = "openvpn_access_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_temp_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_permanent_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    block_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    block_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    block_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QrDownloadToken(Base):
    __tablename__ = "qr_download_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    config_type: Mapped[str] = mapped_column(String(16))
    config_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    max_downloads: Mapped[int] = mapped_column(Integer, default=1)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    pin_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QrDownloadAuditLog(Base):
    __tablename__ = "qr_download_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[int | None] = mapped_column(ForeignKey("qr_download_tokens.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_addr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ViewerConfigAccess(Base):
    __tablename__ = "viewer_config_access"
    __table_args__ = (UniqueConstraint("user_id", "config_group", name="uq_viewer_config_group"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    config_group: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserActionLog(Base):
    __tablename__ = "user_action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_addr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class UserTrafficSample(Base):
    __tablename__ = "user_traffic_sample"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    common_name: Mapped[str] = mapped_column(String(128), index=True)
    network_type: Mapped[str] = mapped_column(String(16), default="vpn")
    protocol_type: Mapped[str] = mapped_column(String(16), default="openvpn")
    delta_received: Mapped[int] = mapped_column(Integer, default=0)
    delta_sent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ProviderCidr(Base):
    __tablename__ = "provider_cidr"
    __table_args__ = (
        UniqueConstraint("provider_key", "cidr", name="uq_provider_cidr_key_cidr"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    cidr: Mapped[str] = mapped_column(String(50))
    region_scope: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    country_codes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ProviderMeta(Base):
    __tablename__ = "provider_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cidr_count: Mapped[int] = mapped_column(Integer, default=0)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    refresh_status: Mapped[str] = mapped_column(String(16), default="never")
    refresh_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_asn_min: Mapped[int] = mapped_column(Integer, default=0)
    asn_count: Mapped[int] = mapped_column(Integer, default=0)
    active_asn_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_level: Mapped[str] = mapped_column(String(16), default="none", index=True)
    anomaly_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ProviderAsn(Base):
    __tablename__ = "provider_asn"
    __table_args__ = (
        UniqueConstraint("provider_key", "asn", name="uq_provider_asn_key_asn"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    asn: Mapped[int] = mapped_column(Integer, index=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    prefix_count: Mapped[int] = mapped_column(Integer, default=0)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ProviderAsnSnapshot(Base):
    __tablename__ = "provider_asn_snapshot"
    __table_args__ = (
        UniqueConstraint("refresh_log_id", "provider_key", "asn", name="uq_provider_asn_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refresh_log_id: Mapped[int] = mapped_column(ForeignKey("cidr_db_refresh_log.id"), index=True)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    asn: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    prefix_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CidrDbRefreshLog(Base):
    __tablename__ = "cidr_db_refresh_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    providers_updated: Mapped[int] = mapped_column(Integer, default=0)
    providers_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_cidrs: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class CidrPreset(Base):
    __tablename__ = "cidr_preset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preset_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    providers_json: Mapped[str] = mapped_column(Text, default="[]")
    settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AntifilterCidr(Base):
    __tablename__ = "antifilter_cidr"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cidr: Mapped[str] = mapped_column(String(50), unique=True, index=True)


class AntifilterMeta(Base):
    __tablename__ = "antifilter_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cidr_count: Mapped[int] = mapped_column(Integer, default=0)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refresh_status: Mapped[str] = mapped_column(String(16), default="never")
    refresh_error: Mapped[str | None] = mapped_column(Text, nullable=True)
