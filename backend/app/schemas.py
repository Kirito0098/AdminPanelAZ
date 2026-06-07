from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import UserRole, VpnType


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.user
    theme: str = "dark"
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=4)


class UserUpdate(BaseModel):
    role: UserRole | None = None
    theme: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4)


class UserResponse(UserBase):
    id: int
    must_change_password: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=4)


class VpnConfigCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    vpn_type: VpnType
    cert_expire_days: int | None = Field(default=3650, ge=1, le=3650)
    description: str | None = None
    owner_id: int | None = None


class VpnConfigUpdate(BaseModel):
    description: str | None = None
    cert_expire_days: int | None = Field(default=None, ge=1, le=3650)
    owner_id: int | None = None


class VpnConfigResponse(BaseModel):
    id: int
    client_name: str
    vpn_type: VpnType
    owner_id: int
    owner_username: str | None = None
    cert_expire_days: int | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    profile_files: list[dict[str, str]] = []

    model_config = {"from_attributes": True}


class ProfileFile(BaseModel):
    protocol: str
    variant: str
    filename: str
    path: str
    content: str | None = None


class MonitoringService(BaseModel):
    name: str
    status: str
    active: bool
    description: str | None = None


class OpenVpnClient(BaseModel):
    common_name: str
    real_address: str
    virtual_address: str
    bytes_received: int
    bytes_sent: int
    connected_since: str


class WireGuardPeer(BaseModel):
    interface: str
    public_key: str
    endpoint: str | None = None
    allowed_ips: str | None = None
    latest_handshake: str | None = None
    transfer_rx: int = 0
    transfer_tx: int = 0
    client_name: str | None = None


class MonitoringOverview(BaseModel):
    services: list[MonitoringService]
    openvpn_clients: list[OpenVpnClient]
    wireguard_peers: list[WireGuardPeer]
    server_ip: str | None = None
    timestamp: datetime


class AppSettingsResponse(BaseModel):
    theme: str
    app_name: str
    antizapret_path: str
    include_hosts: str = ""
    exclude_hosts: str = ""
    include_ips: str = ""


class AppSettingsUpdate(BaseModel):
    theme: str | None = None
    include_hosts: str | None = None
    exclude_hosts: str | None = None
    include_ips: str | None = None


class MessageResponse(BaseModel):
    message: str
    detail: Any | None = None
