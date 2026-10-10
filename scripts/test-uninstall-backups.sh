#!/usr/bin/env bash
# uninstall --remove-backups (его передаёт install.sh --purge-all) удаляет из BACKUP_ROOT только архивы
# панели и их служебные файлы, каталог — только если он опустел. BACKUP_ROOT читается из backend/.env:
# системный каталог (/, /etc, /var, /root, /var/backups …) не трогается вообще.
# Для путей вне временного каталога rm и rmdir подменяются: тест ничего не удаляет на сервере.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FNS="$(for fn in backup_root_is_system_path remove_backup_dir; do
  sed -n "/^${fn}() {/,/^}/p" "$ROOT_DIR/scripts/uninstall.sh"
done)"
if [[ "$FNS" != *"remove_backup_dir() {"* ]]; then
  echo "  FAIL remove_backup_dir не найдена в uninstall.sh" >&2
  exit 1
fi

FAKE_ROOT="$TMP/root"
mkdir -p "$FAKE_ROOT/backend"
CALLS="$TMP/calls.log"
rc=0

pass=0
fail=0
ok() { pass=$((pass + 1)); echo "  OK  $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1" >&2; }

# run_remove <BACKUP_ROOT> [stub]: со stub rm и rmdir только пишутся в $CALLS.
run_remove() {
  local backup_root="$1" stub="${2:-}"
  if [[ -z "$stub" && "$backup_root" != "$TMP"/* ]]; then
    echo "  FAIL $backup_root вне $TMP без подмены rm — тест остановлен" >&2
    exit 1
  fi
  printf 'BACKUP_ROOT=%s\n' "$backup_root" >"$FAKE_ROOT/backend/.env"
  : >"$CALLS"
  set +e
  ROOT_DIR="$FAKE_ROOT" CALLS="$CALLS" STUB="$stub" bash -c '
    set -euo pipefail
    log() { echo "LOG $*"; }
    warn() { echo "WARN $*"; }
    if [[ -n "$STUB" ]]; then
      rm() { echo "rm $*" >>"$CALLS"; }
      rmdir() { echo "rmdir $*" >>"$CALLS"; }
    fi
    REMOVE_BACKUPS=true
    eval "$1"
    remove_backup_dir
  ' bash "$FNS" >"$TMP/out" 2>&1
  rc=$?
  set -e
}

# seed_backups <каталог>: архивы панели, метаданные, недописанный архив, временные файлы, копии перед восстановлением
seed_backups() {
  local dir="$1"
  rm -rf "$dir"
  mkdir -p "$dir/.pre-restore/20261010-101010"
  touch "$dir/adminpanelaz_20261010_101010_000001.tar.gz" "$dir/adminpanelaz_20261010_101010_000001.json" \
    "$dir/adminpanelaz_20260901_090000_upload.tar.gz" "$dir/adminpanelaz_20250101_000000.tar.json" \
    "$dir/.adminpanelaz_20261010_111111_000002.tar.gz.partial" "$dir/.tmp_az-awg2-backup.tar.gz" \
    "$dir/.tmp_include-hosts.txt" "$dir/.pre-restore/20261010-101010/adminpanel.db"
}

echo "[test] в каталоге только файлы панели: удаляются, каталог тоже"
seed_backups "$TMP/backups"
run_remove "$TMP/backups"
[[ "$rc" -eq 0 ]] && ok "удаление прошло" || bad "код $rc: $(cat "$TMP/out")"
if [[ ! -e "$TMP/backups" ]]; then
  ok "каталог бэкапов удалён"
else
  bad "каталог остался: $(cd "$TMP/backups" && find . -mindepth 1 | LC_ALL=C sort | tr '\n' ' ')"
fi

echo "[test] в каталоге чужие файлы: удаляются только файлы панели, каталог остаётся"
seed_backups "$TMP/backups"
mkdir -p "$TMP/backups/other-app"
touch "$TMP/backups/notes.txt" "$TMP/backups/site.tar.gz" "$TMP/backups/other-app/db.sql"
run_remove "$TMP/backups"
left="$(cd "$TMP/backups" 2>/dev/null && find . -mindepth 1 | LC_ALL=C sort | tr '\n' ' ' || true)"
if [[ "$left" == "./notes.txt ./other-app ./other-app/db.sql ./site.tar.gz " ]]; then
  ok "остались только чужие файлы"
else
  bad "осталось: '$left'"
fi
grep -q "оставлен" "$TMP/out" && ok "сказано, что каталог оставлен" || bad "нет сообщения: $(cat "$TMP/out")"

echo "[test] BACKUP_ROOT с .. и / на конце"
seed_backups "$TMP/backups"
run_remove "$TMP/x/../backups/"
[[ ! -e "$TMP/backups" ]] && ok "каталог найден и удалён" || bad "каталог остался: $(cat "$TMP/out")"

echo "[test] каталога нет — без ошибки"
run_remove "$TMP/missing"
[[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
grep -q "не найден" "$TMP/out" && ok "сказано, что каталога нет" || bad "нет сообщения: $(cat "$TMP/out")"

ln -s /etc "$TMP/etc-link"
for root in / /etc /etc/ /var /var/backups /var/lib /usr /usr/local /root /home /opt \
  /var/backups/../../etc "$TMP/etc-link"; do
  echo "[test] BACKUP_ROOT=$root — системный каталог не трогается"
  run_remove "$root" stub
  [[ "$rc" -eq 0 ]] && ok "код 0" || bad "код $rc: $(cat "$TMP/out")"
  [[ ! -s "$CALLS" ]] && ok "rm и rmdir не вызывались" || bad "вызовы: $(tr '\n' ';' <"$CALLS")"
  grep -q "^WARN .*системный каталог" "$TMP/out" && ok "предупреждение" || bad "нет предупреждения: $(cat "$TMP/out")"
done

echo "[test] BACKUP_ROOT не абсолютный путь — ничего не удаляется"
run_remove "backups" stub
[[ ! -s "$CALLS" ]] && ok "rm и rmdir не вызывались" || bad "вызовы: $(tr '\n' ';' <"$CALLS")"
grep -q "^WARN .*не абсолютный" "$TMP/out" && ok "предупреждение" || bad "нет предупреждения: $(cat "$TMP/out")"

echo "Passed: $pass  Failed: $fail"
[[ "$fail" -eq 0 ]]
