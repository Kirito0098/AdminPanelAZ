#!/usr/bin/env python3
"""Apply resource profile to backend/.env (single source: feature_toggles.PROFILE_PRESETS)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.feature_toggles import FeatureToggleService, VALID_RESOURCE_PROFILES  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Minimal/Standard/Full resource profile to .env")
    parser.add_argument("profile", choices=sorted(VALID_RESOURCE_PROFILES))
    parser.add_argument(
        "--env",
        type=Path,
        default=BACKEND / ".env",
        help="Path to backend .env (default: backend/.env)",
    )
    args = parser.parse_args()
    service = FeatureToggleService(args.env)
    result = service.apply_resource_profile(args.profile)
    print(f"Applied profile: {result['profile']} (requires_restart={result['requires_restart']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
