import glob
import json
import os
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status


class BackupManager:
    CONFIG_FILES = (
        "include-hosts.txt",
        "exclude-hosts.txt",
        "include-ips.txt",
        "exclude-ips.txt",
        "allow-ips.txt",
    )

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

    def list_backups(self) -> list[dict]:
        self.backup_root.mkdir(parents=True, exist_ok=True)
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

    def create_backup(self, *, include_configs: bool = False, config_contents: dict[str, str] | None = None) -> dict:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_name = f"adminpanelaz_{timestamp}.tar.gz"
        archive_path = self.backup_root / archive_name

        components: list[str] = []
        summary_parts: list[str] = []

        with tarfile.open(archive_path, "w:gz") as tar:
            if self.db_path.exists():
                tar.add(self.db_path, arcname="data/adminpanel.db")
                components.append("db")
                summary_parts.append("DB:1")

            if self.cidr_db_path is not None and self.cidr_db_path.exists():
                tar.add(self.cidr_db_path, arcname="data/cidr/cidr.db")
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
                        tmp.write_text(content, encoding="utf-8")
                        tar.add(tmp, arcname=f"antizapret/config/{filename}")
                    finally:
                        if tmp.exists():
                            tmp.unlink()
                if config_contents:
                    components.append("configs")
                    summary_parts.append(f"CONFIGS:{len(config_contents)}")

        metadata = {
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "components": components,
            "summary": ",".join(summary_parts),
        }
        meta_path = archive_path.with_suffix(".json")
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        self._enforce_retention(5)
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
        self.backup_root.mkdir(parents=True, exist_ok=True)

        target_name = self._upload_target_name(original_name)
        target_path = self.backup_root / target_name
        if target_path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            target_name = f"adminpanelaz_{stamp}_upload.tar.gz"
            target_path = self.backup_root / target_name

        shutil.move(str(source), str(target_path))
        meta_path = target_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(
                {
                    "created_at": metadata["created_at"],
                    "components": metadata["components"],
                    "summary": metadata["summary"],
                    "source": "upload",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "file_name": target_name,
            "file_path": str(target_path),
            "size_bytes": target_path.stat().st_size,
            "created_at": metadata["created_at"],
            "components": metadata["components"],
            "summary": metadata["summary"],
        }

    def restore_backup(self, file_name: str) -> dict:
        archive_path = self._resolve_archive(file_name)
        restored: list[str] = []

        with tarfile.open(archive_path, "r:gz") as tar:
            members = {m.name: m for m in tar.getmembers()}
            if "data/adminpanel.db" in members:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                extracted = tar.extractfile(members["data/adminpanel.db"])
                if extracted:
                    self.db_path.write_bytes(extracted.read())
                    restored.append("db")

            if "data/cidr/cidr.db" in members and self.cidr_db_path is not None:
                self.cidr_db_path.parent.mkdir(parents=True, exist_ok=True)
                extracted = tar.extractfile(members["data/cidr/cidr.db"])
                if extracted:
                    self.cidr_db_path.write_bytes(extracted.read())
                    restored.append("cidr_db")

            if "env/.env" in members:
                extracted = tar.extractfile(members["env/.env"])
                if extracted:
                    self.env_path.write_bytes(extracted.read())
                    restored.append("env")

        if not restored:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Архив не содержит данных для восстановления")
        return {"restored": restored, "file_name": file_name}

    def delete_backup(self, file_name: str) -> None:
        archive_path = self._resolve_archive(file_name)
        archive_path.unlink(missing_ok=True)
        meta_path = archive_path.with_suffix(".json")
        meta_path.unlink(missing_ok=True)

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

    def _validate_tar_members(self, tar: tarfile.TarFile) -> None:
        for member in tar.getmembers():
            name = member.name.replace("\\", "/")
            if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Архив содержит недопустимые пути",
                )

    def _read_metadata(self, archive_path: Path) -> dict:
        meta_path = archive_path.with_suffix(".json")
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
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
                meta = old.replace(".tar.gz", ".json")
                if os.path.exists(meta):
                    os.remove(meta)
            except OSError:
                pass
