from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from .models import InputHelper, InputHelperCreate, InputHelperRecord, InputHelperUpdate, InputValue


class InputHelperStore:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self._file_path.exists():
            self._write({"inputs": []})

    def list_helpers(self) -> List[InputHelper]:
        data = self._read()
        return [InputHelper(**item) for item in data.get("inputs", [])]

    def get_helper(self, slug: str) -> Optional[InputHelperRecord]:
        for item in self._read().get("inputs", []):
            if item.get("slug") == slug:
                helper = InputHelper(**item)
                return InputHelperRecord(helper)
        return None

    def create_helper(self, payload: InputHelperCreate) -> InputHelper:
        record = InputHelperRecord.create(payload)
        existing = self.get_helper(record.helper.slug)
        if existing is not None:
            raise ValueError(f"Helper with slug '{record.helper.slug}' already exists.")

        with self._lock:
            data = self._read()
            data.setdefault("inputs", []).append(record.as_dict())
            self._write(data)
        return record.helper

    def update_helper(self, slug: str, payload: InputHelperUpdate) -> InputHelper:
        with self._lock:
            data = self._read()
            inputs = data.setdefault("inputs", [])
            for idx, item in enumerate(inputs):
                if item.get("slug") == slug:
                    record = InputHelperRecord(InputHelper(**item))
                    record.update(payload)
                    inputs[idx] = record.as_dict()
                    self._write(data)
                    return record.helper
        raise KeyError(f"Helper '{slug}' not found.")

    def delete_helper(self, slug: str) -> None:
        with self._lock:
            data = self._read()
            inputs = data.setdefault("inputs", [])
            new_inputs = [item for item in inputs if item.get("slug") != slug]
            if len(new_inputs) == len(inputs):
                raise KeyError(f"Helper '{slug}' not found.")
            data["inputs"] = new_inputs
            self._write(data)

    def set_last_value(self, slug: str, value: InputValue) -> InputHelper:
        with self._lock:
            data = self._read()
            inputs = data.setdefault("inputs", [])
            for idx, item in enumerate(inputs):
                if item.get("slug") == slug:
                    record = InputHelperRecord(InputHelper(**item))
                    record.touch_last_value(value)
                    inputs[idx] = record.as_dict()
                    self._write(data)
                    return record.helper
        raise KeyError(f"Helper '{slug}' not found.")

    def _read(self) -> Dict[str, List[dict]]:
        if not self._file_path.exists():
            return {"inputs": []}
        with self._file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, data: Dict[str, List[dict]]) -> None:
        tmp_path = self._file_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        tmp_path.replace(self._file_path)


__all__ = ["InputHelperStore"]
