#!/usr/bin/env bash
# Пакеты apt установщика: их ставит install.sh (install_system_deps) и доустанавливает install.sh --update.
# Python (pythonX.Y, -venv, -dev) — scripts/python-runtime.sh, Node.js — install_nodejs в install.sh.
# shellcheck disable=SC2034
ADMINPANELAZ_APT_PACKAGES=(python3-pip git curl build-essential ca-certificates pkg-config libffi-dev libssl-dev vnstat)
