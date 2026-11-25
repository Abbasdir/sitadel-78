"""Lecture et écriture des caches JSONL et des CSV de revue.

Les historiques sont en ajout seul : une ligne écrite n'est jamais réécrite, car l'identifiant
d'une décision est l'empreinte de son contenu exact.
"""
from __future__ import annotations

import csv
import json
import re
import warnings
from pathlib import Path
from typing import Iterable

from .config import CACHE_GEMINI, CACHE_OLLAMA, CACHE_WEB


def _is_siren(value) -> bool:
    return bool(re.fullmatch(r"\d{9}", str(value)))


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def load_history(path: Path) -> list[dict]:
    """Réponses LLM d'un fichier, dans l'ordre d'écriture ; une ligne illisible est signalée et ignorée."""
    if not path.exists():
        return []
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            warnings.warn(f"Cache LLM : ligne {number} illisible, ignorée.")
            continue
        if isinstance(record, dict) and _is_siren(record.get("siren", "")):
            records.append(record)
    return records


def load_all_history(folder: Path | None = None) -> list[dict]:
    """Historique Ollama (lecture seule) + Gemini, trié par date, sans rien effacer."""
    ollama = folder / CACHE_OLLAMA.name if folder else CACHE_OLLAMA
    gemini = folder / CACHE_GEMINI.name if folder else CACHE_GEMINI
    records = load_history(ollama) + load_history(gemini)
    return sorted(records, key=lambda record: str(record.get("horodatage", "")))


def load_web_latest(path: Path = CACHE_WEB) -> dict[str, dict]:
    """Dernière recherche web connue par SIREN."""
    latest = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and _is_siren(record.get("siren", "")):
                latest[record["siren"]] = record
    return latest


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_atomic(path: Path, columns: list[str], rows: Iterable[dict]) -> None:
    """Écrit dans un fichier temporaire puis remplace : un échec ne laisse pas de CSV tronqué."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
