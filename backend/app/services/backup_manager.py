import glob
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from app.services.atomic_file import atomic_write_bytes

logger = logging.getLogger(__name__)


def remove_sqlite_sidecars(db_path: Path) -> None:
    """Remove SQLite WAL/SHM files so a restored .db is opened cleanly."""
    for suffix in ("-wal", "-shm"):
        try:
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


_SQLITE_HEADER = b"SQLite format 3\x00"
_PRE_RESTORE_STAMP = "%Y%m%d_%H%M%S_%f"
_PRE_RESTORE_ID = re.compile(r"\d{8}_\d{6}_\d{6}")


def validate_sqlite_bytes(data: bytes, label: str) -> None:
    """Reject a restore before any live file is touched if the archived database is damaged."""
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{label} в архиве повреждена — восстановление отменено, текущие данные не изменены",
    )
    if not data.startswith(_SQLITE_HEADER):
        raise invalid
    # A WAL-mode copy grows -wal/-shm next to itself even when opened read-only.
    with tempfile.TemporaryDirectory(prefix="adminpanelaz-restore-check-") as tmp_dir:
        tmp = Path(tmp_dir) / "check.db"
        tmp.write_bytes(data)
        try:
            conn = sqlite3.connect(f"file:{tmp.as_posix()}?mode=ro", uri=True)
            try:
                result = conn.execute("PRAGMA integrity_check(1)").fetchone()
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            raise invalid from exc
    if not result or result[0] != "ok":
        raise invalid


def _write_private_bytes(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def backup_meta_path(archive_path: Path) -> Path:
    """Sidecar JSON next to a .tar.gz archive (not Path.with_suffix, which yields .tar.json)."""
    name = archive_path.name
    if name.endswith(".tar.gz"):
        return archive_path.with_name(name[: -len(".tar.gz")] + ".json")
    return archive_path.with_suffix(".json")


class BackupManager:
    CONFIG_FILES = (
        "include-hosts.txt",
        "exclude-hosts.txt",
        "include-ips.txt",
        "exclude-ips.txt",
        "allow-ips.txt",
    )
    AWG2_ARCHIVE_MEMBER = "awg2/az-awg2-backup.tar.gz"
    PRE_RESTORE_DIR = ".pre-restore"
    PRE_RESTORE_KEEP = 3
    PRE_RESTORE_NAMES = {"db": "adminpanel.db", "cidr_db": "cidr.db", "env": ".env"}
    SQLITE_ROLES = frozenset({"db", "cidr_db"})
    RESTORE_FREE_SPACE_MARGIN = 64 * 1024 * 1024

    def __init__(
        self,
        *,
        app_root: Path,
        backup_root: Path,
        db_path: Path,
        env_path: Path,
        cidr_db_path: Path | None = None,
    ):
        self.app_root = app_root.resolve()
        self.backup_root = backup_root.resolve()
        self.db_path = db_path.resolve()
        self.env_path = env_path.resolve()
        self.cidr_db_path = cidr_db_path.resolve() if cidr_db_path is not None else None

    def _ensure_backup_root(self) -> None:
        # Archives hold the panel DB and .env.
        self.backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            if self.backup_root.stat().st_mode & 0o077:
                os.chmod(self.backup_root, 0o700)
        except OSError as exc:
            logger.warning("Could not restrict permissions on %s: %s", self.backup_root, exc)

    def list_backups(self) -> list[dict]:
        self._ensure_backup_root()
        archives = sorted(
            self.backup_root.glob("*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        result = []
        for path in archives:
            try:
                stat = path.stat()
            except OSError:
                continue
            metadata = self._read_metadata(path)
            result.append({
                "file_name": path.name,
                "size_bytes": stat.st_size,
                "created_at": metadata.get("created_at")
                or datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "components": metadata.get("components", []),
                "summary": metadata.get("summary", ""),
            })
        return result

    def create_backup(
        self,
        *,
        include_configs: bool = False,
        config_contents: dict[str, str] | None = None,
        retention: int = 5,
        awg2_archive: bytes | None = None,
    ) -> dict:
        self._ensure_backup_root()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        archive_name = f"adminpanelaz_{timestamp}.tar.gz"
        archive_path = self.backup_root / archive_name

        components: list[str] = []
        summary_parts: list[str] = []

        _write_private_bytes(archive_path, b"")
        with tarfile.open(archive_path, "w:gz") as tar:
            if self.db_path.exists():
                self._add_sqlite_snapshot(tar, self.db_path, "data/adminpanel.db")
                components.append("db")
                summary_parts.append("DB:1")

            if self.cidr_db_path is not None and self.cidr_db_path.exists():
                self._add_sqlite_snapshot(tar, self.cidr_db_path, "data/cidr/cidr.db")
                components.append("cidr_db")
                summary_parts.append("CIDR_DB:1")

            if self.env_path.exists():
                tar.add(self.env_path, arcname="env/.env")
                components.append("env")
                summary_parts.append("ENV:1")

            if include_configs and config_contents:
                for filename, content in config_contents.items():
                    if filename not in self.CONFIG_FILES:
                        continue
                    tmp = self.backup_root / f".tmp_{filename}"
                    try:
                        _write_private_bytes(tmp, content.encode("utf-8"))
                        tar.add(tmp, arcname=f"antizapret/config/{filename}")
                    finally:
                        if tmp.exists():
                            tmp.unlink()
                if config_contents:
                    components.append("configs")
                    summary_parts.append(f"CONFIGS:{len(config_contents)}")

            if awg2_archive:
                tmp = self.backup_root / ".tmp_az-awg2-backup.tar.gz"
                try:
                    _write_private_bytes(tmp, awg2_archive)
                    tar.add(tmp, arcname=self.AWG2_ARCHIVE_MEMBER)
                finally:
                    tmp.unlink(missing_ok=True)
                components.append("awg2")
                summary_parts.append("AWG2:1")

        metadata = {
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "components": components,
            "summary": ",".join(summary_parts),
        }
        meta_path = backup_meta_path(archive_path)
        atomic_write_bytes(meta_path, json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"))

        self._enforce_retention(max(1, int(retention)))
        return {
            "file_name": archive_name,
            "file_path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
            **metadata,
        }

    def inspect_backup_archive(self, archive_path: Path) -> dict:
        path = archive_path.resolve()
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл архива не найден")
        try:
            with tarfile.open(path, "r:gz") as tar:
                self._validate_tar_members(tar)
                member_names = {m.name for m in tar.getmembers()}
        except tarfile.TarError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректный архив .tar.gz",
            ) from exc

        components: list[str] = []
        if "data/adminpanel.db" in member_names:
            components.append("db")
        if "data/cidr/cidr.db" in member_names:
            components.append("cidr_db")
        if "env/.env" in member_names:
            components.append("env")
        if any(name.startswith("antizapret/config/") for name in member_names):
            components.append("configs")
        if self.AWG2_ARCHIVE_MEMBER in member_names:
            components.append("awg2")

        if not components:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Архив не похож на резервную копию AdminPanel (нет БД, CIDR или .env)",
            )

        created_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "components": components,
            "summary": ",".join(components),
            "created_at": created_at,
        }

    def import_uploaded_backup(self, source_path: Path, *, original_name: str | None = None) -> dict:
        source = source_path.resolve()
        metadata = self.inspect_backup_archive(source)
        self._ensure_backup_root()

        target_name = self._upload_target_name(original_name)
        target_path = self.backup_root / target_name
        if target_path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            target_name = f"adminpanelaz_{stamp}_upload.tar.gz"
            target_path = self.backup_root / target_name

        shutil.move(str(source), str(target_path))
        os.chmod(target_path, 0o600)
        meta_path = backup_meta_path(target_path)
        atomic_write_bytes(
            meta_path,
            json.dumps(
                {
                    "created_at": metadata["created_at"],
                    "components": metadata["components"],
                    "summary": metadata["summary"],
                    "source": "upload",
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )
        return {
            "file_name": target_name,
            "file_path": str(target_path),
            "size_bytes": target_path.stat().st_size,
            "created_at": metadata["created_at"],
            "components": metadata["components"],
            "summary": metadata["summary"],
        }

    def load_restore_payload(self, file_name: str) -> dict:
        archive_path = self._resolve_archive(file_name)
        restored: list[str] = []
        restored_configs: dict[str, str] = {}
        files: dict[str, bytes] = {}

        with tarfile.open(archive_path, "r:gz") as tar:
            members = {m.name: m for m in tar.getmembers()}
            if "data/adminpanel.db" in members:
                extracted = tar.extractfile(members["data/adminpanel.db"])
                if extracted:
                    files["db"] = extracted.read()
                    restored.append("db")

            if "data/cidr/cidr.db" in members and self.cidr_db_path is not None:
                extracted = tar.extractfile(members["data/cidr/cidr.db"])
                if extracted:
                    files["cidr_db"] = extracted.read()
                    restored.append("cidr_db")

            if "env/.env" in members:
                extracted = tar.extractfile(members["env/.env"])
                if extracted:
                    files["env"] = extracted.read()
                    restored.append("env")

            for filename in self.CONFIG_FILES:
                member_name = f"antizapret/config/{filename}"
                if member_name not in members:
                    continue
                extracted = tar.extractfile(members[member_name])
                if not extracted:
                    continue
                restored_configs[filename] = extracted.read().decode("utf-8")
            if restored_configs:
                restored.append("configs")

            if self.AWG2_ARCHIVE_MEMBER in members:
                extracted = tar.extractfile(members[self.AWG2_ARCHIVE_MEMBER])
                if extracted:
                    files["awg2"] = extracted.read()
                    restored.append("awg2")

        if not restored:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Архив не содержит данных для восстановления",
            )
        if "db" in files:
            validate_sqlite_bytes(files["db"], "База панели")
        if "cidr_db" in files:
            validate_sqlite_bytes(files["cidr_db"], "База CIDR")
        self._ensure_restore_space(self._restore_targets(files))
        return {
            "restored": restored,
            "file_name": file_name,
            "configs": restored_configs,
            "_files": files,
        }

    def _restore_targets(self, files: dict[str, bytes]) -> list[tuple[str, Path, bytes]]:
        targets: list[tuple[str, Path, bytes]] = []
        if "db" in files:
            targets.append(("db", self.db_path, files["db"]))
        if "cidr_db" in files and self.cidr_db_path is not None:
            targets.append(("cidr_db", self.cidr_db_path, files["cidr_db"]))
        if "env" in files:
            targets.append(("env", self.env_path, files["env"]))
        return targets

    def _ensure_restore_space(self, targets: list[tuple[str, Path, bytes]]) -> None:
        """Refuse up front: running out of disk mid-restore would happen after node overlays were applied."""
        required: dict[int, tuple[Path, int]] = {}

        def need(directory: Path, size: int) -> None:
            directory.mkdir(parents=True, exist_ok=True)
            dev = directory.stat().st_dev
            anchor, total = required.get(dev, (directory, 0))
            required[dev] = (anchor, total + size)

        for _role, path, data in targets:
            if path.exists():
                need(self.backup_root, path.stat().st_size)
            need(path.parent, len(data))
        for anchor, size in required.values():
            if shutil.disk_usage(anchor).free < size + self.RESTORE_FREE_SPACE_MARGIN:
                raise HTTPException(
                    status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                    detail=f"Недостаточно места на диске для восстановления ({anchor}) — текущие данные не изменены",
                )

    def apply_restore_payload(self, payload: dict) -> dict:
        targets = self._restore_targets(payload.get("_files") or {})
        snapshot = self._snapshot_live_files([(role, path) for role, path, _data in targets]) if targets else None
        replaced: list[tuple[str, Path]] = []
        try:
            for role, path, data in targets:
                atomic_write_bytes(path, data)
                replaced.append((role, path))
                if role in self.SQLITE_ROLES:
                    # A leftover WAL of the old database would be replayed onto the restored file.
                    remove_sqlite_sidecars(path)
        except BaseException:
            self._rollback_from_snapshot(replaced, snapshot)
            raise
        if snapshot is not None:
            self._carry_over_telegram_updates(snapshot / self.PRE_RESTORE_NAMES["db"])

        result = {
            "restored": list(payload.get("restored") or []),
            "file_name": payload.get("file_name"),
            "configs": dict(payload.get("configs") or {}),
        }
        if snapshot is not None:
            result["pre_restore_snapshot"] = str(snapshot)
        return result

    def _carry_over_telegram_updates(self, live_copy: Path) -> None:
        if not live_copy.is_file():
            return
        from app.services import telegram_update_dedup

        try:
            telegram_update_dedup.carry_over_processed_updates(live_copy, self.db_path)
        except Exception:
            logger.exception(
                "Restore: Telegram update ids were not carried over to the restored DB; "
                "a redelivered bot command may run again"
            )

    def _snapshot_live_files(self, targets: list[tuple[str, Path]]) -> Path:
        """Copy the files a restore is about to replace, so a bad restore can be undone by hand."""
        root = self.backup_root / self.PRE_RESTORE_DIR
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        stamp = datetime.now(timezone.utc).strftime(_PRE_RESTORE_STAMP)
        snapshot = root / stamp
        snapshot.mkdir(mode=0o700)
        os.chmod(snapshot, 0o700)
        for role, path in targets:
            if not path.exists():
                continue
            dest = snapshot / self.PRE_RESTORE_NAMES[role]
            if not self._copy_sqlite_consistent(path, dest):
                shutil.copyfile(path, dest)
            os.chmod(dest, 0o600)
        self._enforce_pre_restore_retention(root)
        return snapshot

    @staticmethod
    def _copy_sqlite_consistent(src: Path, dest: Path) -> bool:
        """Online-backup copy (includes committed WAL frames); False if ``src`` is not a readable database."""
        with src.open("rb") as fh:
            if fh.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
                return False
        try:
            source = sqlite3.connect(f"file:{src.resolve().as_posix()}?mode=ro", uri=True)
            try:
                target = sqlite3.connect(str(dest))
                try:
                    source.backup(target)
                finally:
                    target.close()
            finally:
                source.close()
        except sqlite3.DatabaseError:
            dest.unlink(missing_ok=True)
            return False
        return True

    def _rollback_from_snapshot(self, replaced: list[tuple[str, Path]], snapshot: Path | None) -> None:
        for role, path in replaced:
            saved = snapshot / self.PRE_RESTORE_NAMES[role] if snapshot is not None else None
            try:
                if saved is not None and saved.exists():
                    atomic_write_bytes(path, saved.read_bytes())
                else:
                    path.unlink(missing_ok=True)
                remove_sqlite_sidecars(path)
            except OSError:
                logger.exception("Restore rollback failed for %s (pre-restore copy: %s)", path, snapshot)

    def _enforce_pre_restore_retention(self, root: Path) -> None:
        snapshots = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)
        for old in snapshots[self.PRE_RESTORE_KEEP :]:
            shutil.rmtree(old, ignore_errors=True)

    def list_pre_restore_snapshots(self) -> list[dict]:
        root = self.backup_root / self.PRE_RESTORE_DIR
        if not root.is_dir():
            return []
        result = []
        snapshots = (p for p in root.iterdir() if p.is_dir() and _PRE_RESTORE_ID.fullmatch(p.name))
        for snapshot in sorted(snapshots, key=lambda p: p.name, reverse=True):
            files = {
                role: snapshot / name
                for role, name in self.PRE_RESTORE_NAMES.items()
                if (snapshot / name).is_file()
            }
            created_at = datetime.strptime(snapshot.name, _PRE_RESTORE_STAMP).replace(tzinfo=timezone.utc)
            result.append({
                "snapshot_id": snapshot.name,
                "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "size_bytes": sum(path.stat().st_size for path in files.values()),
                "components": list(files),
            })
        return result

    def _resolve_pre_restore_snapshot(self, snapshot_id: str) -> Path:
        snapshot = self.backup_root / self.PRE_RESTORE_DIR / snapshot_id
        if not _PRE_RESTORE_ID.fullmatch(snapshot_id) or not snapshot.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Копия перед восстановлением не найдена")
        return snapshot

    def load_pre_restore_payload(self, snapshot_id: str) -> dict:
        """Roll back a restore: the copy holds only the DB, CIDR DB and .env it replaced."""
        snapshot = self._resolve_pre_restore_snapshot(snapshot_id)
        files: dict[str, bytes] = {}
        for role, name in self.PRE_RESTORE_NAMES.items():
            if role == "cidr_db" and self.cidr_db_path is None:
                continue
            path = snapshot / name
            if path.is_file():
                files[role] = path.read_bytes()
        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Копия перед восстановлением пуста")
        if "db" in files:
            validate_sqlite_bytes(files["db"], "База панели")
        if "cidr_db" in files:
            validate_sqlite_bytes(files["cidr_db"], "База CIDR")
        self._ensure_restore_space(self._restore_targets(files))
        return {"restored": list(files), "file_name": snapshot_id, "configs": {}, "_files": files}

    def delete_pre_restore_snapshot(self, snapshot_id: str) -> None:
        shutil.rmtree(self._resolve_pre_restore_snapshot(snapshot_id))

    def restore_backup(self, file_name: str) -> dict:
        return self.apply_restore_payload(self.load_restore_payload(file_name))

    def delete_backup(self, file_name: str) -> None:
        archive_path = self._resolve_archive(file_name)
        archive_path.unlink(missing_ok=True)
        backup_meta_path(archive_path).unlink(missing_ok=True)
        archive_path.with_suffix(".json").unlink(missing_ok=True)

    def get_backup_path(self, file_name: str) -> Path:
        return self._resolve_archive(file_name)

    def _resolve_archive(self, file_name: str) -> Path:
        safe_name = os.path.basename(file_name)
        if not safe_name.endswith(".tar.gz"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимое имя архива")

        if os.path.isabs(file_name):
            candidate = Path(file_name).resolve()
            if candidate.is_file():
                return candidate

        path = (self.backup_root / safe_name).resolve()
        if not str(path).startswith(str(self.backup_root)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый путь")
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Архив не найден")
        return path

    def _upload_target_name(self, original_name: str | None) -> str:
        safe_name = os.path.basename(original_name or "").strip()
        if safe_name.endswith(".tar.gz") and safe_name.startswith("adminpanelaz_"):
            return safe_name
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"adminpanelaz_{stamp}_upload.tar.gz"

    def _add_sqlite_snapshot(self, tar: tarfile.TarFile, db_path: Path, arcname: str) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix="adminpanelaz-bak-", suffix=".db")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            src = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
            try:
                dst = sqlite3.connect(str(tmp))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            tar.add(tmp, arcname=arcname)
        finally:
            tmp.unlink(missing_ok=True)
            Path(f"{tmp}-wal").unlink(missing_ok=True)
            Path(f"{tmp}-shm").unlink(missing_ok=True)

    def _validate_tar_members(self, tar: tarfile.TarFile) -> None:
        for member in tar.getmembers():
            name = member.name.replace("\\", "/")
            if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Архив содержит недопустимые пути",
                )

    def _read_metadata(self, archive_path: Path) -> dict:
        for meta_path in (backup_meta_path(archive_path), archive_path.with_suffix(".json")):
            if meta_path.exists():
                try:
                    return json.loads(meta_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
        return {}

    def _enforce_retention(self, count: int) -> None:
        archives = sorted(
            glob.glob(str(self.backup_root / "*.tar.gz")),
            key=os.path.getmtime,
            reverse=True,
        )
        for old in archives[count:]:
            try:
                os.remove(old)
                old_path = Path(old)
                backup_meta_path(old_path).unlink(missing_ok=True)
                old_path.with_suffix(".json").unlink(missing_ok=True)
            except OSError:
                pass
