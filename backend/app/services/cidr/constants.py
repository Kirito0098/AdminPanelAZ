"""CIDR provider catalog (ported from AdminAntizapret)."""

IP_FILES: dict[str, dict[str, str | list[str]]] = {
    "akamai-ips.txt": {
        "name": "Akamai",
        "description": "Маршрутизация сетей Akamai через Antizapret (CDN и edge-сервисы).",
        "category": "cdn",
        "tags": ["cdn", "streaming", "enterprise"],
    },
    "amazon-ips.txt": {
        "name": "Amazon",
        "description": "Маршрутизация сетей Amazon/AWS через Antizapret.",
        "category": "cloud",
        "tags": ["cloud", "gaming", "social", "streaming"],
    },
    "digitalocean-ips.txt": {
        "name": "DigitalOcean",
        "description": "Маршрутизация сетей DigitalOcean через Antizapret.",
        "category": "hosting",
        "tags": ["hosting", "gaming"],
    },
    "google-ips.txt": {
        "name": "Google",
        "description": "Маршрутизация сетей Google/Google Cloud через Antizapret.",
        "category": "cloud",
        "tags": ["cloud", "streaming", "enterprise", "mobile"],
    },
    "hetzner-ips.txt": {
        "name": "Hetzner",
        "description": "Маршрутизация сетей Hetzner через Antizapret.",
        "category": "hosting",
        "tags": ["hosting", "gaming", "europe"],
    },
    "ovh-ips.txt": {
        "name": "OVH",
        "description": "Маршрутизация сетей OVH через Antizapret.",
        "category": "hosting",
        "tags": ["hosting", "gaming", "europe"],
    },
    "cloudflare-ips.txt": {
        "name": "Cloudflare",
        "description": "Маршрутизация сетей Cloudflare через Antizapret.",
        "category": "cdn",
        "tags": ["cdn", "security", "enterprise"],
    },
    "fastly-ips.txt": {
        "name": "Fastly",
        "description": "Маршрутизация сетей Fastly через Antizapret.",
        "category": "cdn",
        "tags": ["cdn", "social", "streaming", "enterprise"],
    },
    "azure-ips.txt": {
        "name": "Microsoft Azure",
        "description": "Маршрутизация сетей Microsoft/Azure через Antizapret.",
        "category": "cloud",
        "tags": ["cloud", "gaming", "social", "enterprise"],
    },
    "oracle-ips.txt": {
        "name": "Oracle",
        "description": "Маршрутизация сетей Oracle Cloud через Antizapret.",
        "category": "cloud",
        "tags": ["cloud", "hosting"],
    },
    "cdn77-ips.txt": {
        "name": "CDN77",
        "description": "Маршрутизация сетей CDN77 через Antizapret.",
        "category": "cdn",
        "tags": ["cdn", "streaming"],
    },
    "m247-ips.txt": {
        "name": "M247",
        "description": "Маршрутизация сетей M247 через Antizapret.",
        "category": "hosting",
        "tags": ["hosting"],
    },
}

ROUTE_CONFIG_FILES = {
    "include_ips": "include-ips.txt",
    "exclude_ips": "exclude-ips.txt",
    "forward_ips": "forward-ips.txt",
    "drop_ips": "drop-ips.txt",
}

RESULT_FILES = {
    "route_ips": "route-ips.txt",
    "keenetic_wg": "keenetic-wireguard-routes.txt",
    "mikrotik_wg": "mikrotik-wireguard-routes.txt",
    "tplink_ovpn": "tp-link-openvpn-routes.txt",
}
