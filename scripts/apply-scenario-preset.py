#!/usr/bin/env python3
"""Apply scenario preset to backend/.env (single source: feature_toggles.SCENARIO_PRESETS)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.feature_toggles import FeatureToggleService, VALID_SCENARIO_PRESETS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply panel_only/home/commercial scenario to .env")
    parser.add_argument("preset", choices=sorted(VALID_SCENARIO_PRESETS))
    parser.add_argument(
        "--env",
        type=Path,
        default=BACKEND / ".env",
        help="Path to backend .env (default: backend/.env)",
    )
    args = parser.parse_args()
    service = FeatureToggleService(args.env)
    result = service.apply_scenario_preset(args.preset)
    print(f"Applied scenario: {result['preset']} (requires_restart={result['requires_restart']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
