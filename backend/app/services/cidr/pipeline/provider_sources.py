"""Provider URLs, game catalog, region scopes, and DPI maps."""
import os
import re

from app.services.cidr.pipeline.constants import (
    GAME_FILTER_BLOCK_END,
    GAME_FILTER_BLOCK_START,
    GAME_FILTER_IP_BLOCK_END,
    GAME_FILTER_IP_BLOCK_START,
    GAME_INCLUDE_HOSTS_FILE,
    GAME_INCLUDE_IPS_FILE,
)

PROVIDER_SOURCES = {
    "akamai-ips.txt": [
        {
            "name": "ripe-as20940-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS20940",
            "format": "ripe_geo_json",
        },
        {
            "name": "ripe-as20940-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS20940",
            "format": "ripe_json",
        },
    ],
    "amazon-ips.txt": [
        {
            "name": "aws-ip-ranges",
            "url": "https://ip-ranges.amazonaws.com/ip-ranges.json",
            "format": "aws_json",
        }
    ],
    "digitalocean-ips.txt": [
        {
            "name": "ripe-as14061-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS14061",
            "format": "ripe_geo_json",
        },
        {
            "name": "ripe-as46652-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS46652",
            "format": "ripe_json",
        },
    ],
    "google-ips.txt": [
        {
            "name": "google-goog-json",
            "url": "https://www.gstatic.com/ipranges/goog.json",
            "format": "google_json",
        },
        {
            "name": "google-cloud-json",
            "url": "https://www.gstatic.com/ipranges/cloud.json",
            "format": "google_json",
        },
    ],
    "hetzner-ips.txt": [
        {
            "name": "ripe-as24940-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS24940",
            "format": "ripe_geo_json",
        },
        {
            "name": "ripe-as213230-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS213230",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as212317-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS212317",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as215859-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS215859",
            "format": "ripe_json",
        }
    ],
    "ovh-ips.txt": [
        {
            "name": "ripe-as16276-geo",
            "url": "https://stat.ripe.net/data/maxmind-geo-lite-announced-by-as/data.json?resource=AS16276",
            "format": "ripe_geo_json",
        },
        {
            "name": "ripe-as35540-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS35540",
            "format": "ripe_json",
        }
    ],
    "cloudflare-ips.txt": [
        {
            "name": "cloudflare-ips-v4",
            "url": "https://www.cloudflare.com/ips-v4",
            "format": "cidr_text",
        },
    ],
    "fastly-ips.txt": [
        {
            "name": "ripe-as54113-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS54113",
            "format": "ripe_json",
        }
    ],
    "azure-ips.txt": [
        {
            "name": "ripe-as8075-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS8075",
            "format": "ripe_json",
        }
    ],
    "oracle-ips.txt": [
        {
            "name": "ripe-as31898-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS31898",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as54253-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS54253",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as1219-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS1219",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as6142-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS6142",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as14544-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS14544",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as20054-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS20054",
            "format": "ripe_json",
        }
    ],
    "cdn77-ips.txt": [
        {
            "name": "ripe-as60068-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS60068",
            "format": "ripe_json",
        },
        {
            "name": "ripe-as212238-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS212238",
            "format": "ripe_json",
        }
    ],
    "m247-ips.txt": [
        {
            "name": "ripe-as9009-announced",
            "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS9009",
            "format": "ripe_json",
        }
    ],
}
STRICT_GEO_BUCKET_SCOPES = (
    "europe",
    "north-america",
    "central-america",
    "south-america",
    "asia-east",
    "asia-south",
    "asia-southeast",
    "oceania",
    "middle-east",
    "africa",
)
STRICT_ASIA_PACIFIC_BUCKETS = {
    "asia-east",
    "asia-south",
    "asia-southeast",
    "oceania",
}

REGION_SCOPES = {
    "all",
    "europe",
    "north-america",
    "central-america",
    "south-america",
    "asia-pacific",
    "asia-east",
    "asia-south",
    "asia-southeast",
    "oceania",
    "middle-east",
    "africa",
    "china",
    "government",
    "global",
}


DPI_NODE_CODE_TO_FILE = {
    "AKM": "akamai-ips.txt",
    "AWS": "amazon-ips.txt",
    "CDN77": "cdn77-ips.txt",
    "CF": "cloudflare-ips.txt",
    "DO": "digitalocean-ips.txt",
    "FST": "fastly-ips.txt",
    "GC": "google-ips.txt",
    "HE": "hetzner-ips.txt",
    "ME": "m247-ips.txt",
    "MS": "azure-ips.txt",
    "OR": "oracle-ips.txt",
    "OVH": "ovh-ips.txt",
}

DPI_PROVIDER_TO_FILE = {
    "Akamai": "akamai-ips.txt",
    "AWS": "amazon-ips.txt",
    "CDN77": "cdn77-ips.txt",
    "Cloudflare": "cloudflare-ips.txt",
    "DigitalOcean": "digitalocean-ips.txt",
    "Fastly": "fastly-ips.txt",
    "Google Cloud": "google-ips.txt",
    "Hetzner": "hetzner-ips.txt",
    "M247 Europe SRL": "m247-ips.txt",
    "Microsoft/Azure": "azure-ips.txt",
    "Oracle": "oracle-ips.txt",
    "OVH": "ovh-ips.txt",
}


def _normalize_provider_name_token(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


DPI_PROVIDER_ALIASES = {
    "aws": "amazon-ips.txt",
    "amazon": "amazon-ips.txt",
    "amazonaws": "amazon-ips.txt",
    "azure": "azure-ips.txt",
    "microsoft": "azure-ips.txt",
    "microsoftazure": "azure-ips.txt",
    "google": "google-ips.txt",
    "googlecloud": "google-ips.txt",
    "gcp": "google-ips.txt",
    "m247": "m247-ips.txt",
}
for _provider_name, _file_name in DPI_PROVIDER_TO_FILE.items():
    _alias = _normalize_provider_name_token(_provider_name)
    if _alias and _alias not in DPI_PROVIDER_ALIASES:
        DPI_PROVIDER_ALIASES[_alias] = _file_name
