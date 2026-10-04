"""Профили поставщиков: запомненные настройки чтения прайса.

Поставщик присылает прайс каждую неделю в одном и том же виде. Один раз
сопоставили колонки — программа запомнит их под именем поставщика
и в следующий раз подставит сама.

Профили хранятся в JSON в папке пользователя:
%APPDATA%\\PriceListMerger\\profiles.json (Windows).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .core.mapping import FIELD_BY_KEY, Mapping


def default_profiles_path() -> Path:
    """Путь к файлу профилей в папке данных пользователя."""
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "PriceListMerger" / "profiles.json"


@dataclass
class SupplierProfile:
    """Что запоминаем о прайсе поставщика."""

    mapping: Mapping = field(default_factory=dict)
    header_row: int | None = None
    sheet: str | None = None


class ProfileStore:
    """Чтение и запись профилей. Ключ — имя поставщика без учёта регистра."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_profiles_path()
        self._profiles: dict[str, SupplierProfile] = {}
        self._load()

    @staticmethod
    def _key(supplier: str) -> str:
        return supplier.strip().lower()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # файла ещё нет или он испорчен — начинаем с пустого списка
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            # Неизвестные поля пропускаем: файл мог отредактировать человек
            mapping = {
                field_key: str(column)
                for field_key, column in (value.get("mapping") or {}).items()
                if field_key in FIELD_BY_KEY and column
            }
            header_row = value.get("header_row")
            self._profiles[key] = SupplierProfile(
                mapping=mapping,
                header_row=header_row if isinstance(header_row, int) else None,
                sheet=value.get("sheet") if isinstance(value.get("sheet"), str) else None,
            )

    def get(self, supplier: str) -> SupplierProfile | None:
        return self._profiles.get(self._key(supplier))

    def names(self) -> list[str]:
        return sorted(self._profiles)

    def save(self, supplier: str, profile: SupplierProfile) -> None:
        """Запоминает профиль и сразу записывает файл."""
        self._profiles[self._key(supplier)] = profile
        self._write()

    def delete(self, supplier: str) -> None:
        if self._profiles.pop(self._key(supplier), None) is not None:
            self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {key: asdict(profile) for key, profile in sorted(self._profiles.items())}
        # Пишем во временный файл и подменяем: при сбое старый файл не пострадает
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
