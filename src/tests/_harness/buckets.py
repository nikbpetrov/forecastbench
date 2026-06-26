"""Local bucket mount helper for GCP-free orchestration tests.

``utils/gcp/storage.py`` routes every bucket operation to a local directory tree when
``BUCKET_MOUNT_POINT`` is set. ``LocalBucket`` wires that env var (plus the ``*_BUCKET`` names)
to a temp dir and offers small helpers to seed inputs and read outputs using the exact
filename conventions ``helpers.data_utils.generate_filenames`` and ``orchestration._source_io``
produce, so tests exercise the real IO paths.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

# Logical bucket roles -> the env var each is read from. Default bucket names below.
_BUCKET_ENV_VARS = {
    "QUESTION_BANK_BUCKET": "question-bank",
    "QUESTION_SETS_BUCKET": "question-sets",
    "FORECAST_SETS_BUCKET": "forecast-sets",
    "PROCESSED_FORECAST_SETS_BUCKET": "processed-forecast-sets",
    "PUBLIC_RELEASE_BUCKET": "public-release",
    "WORKSPACE_BUCKET": "workspace",
}


class LocalBucket:
    """A temp-dir-backed stand-in for the project's GCS buckets."""

    def __init__(self, root: Path):
        """Create the mount root and per-bucket subdirectories.

        Args:
            root (Path): Temp directory used as ``BUCKET_MOUNT_POINT``.
        """
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.bucket_names = dict(_BUCKET_ENV_VARS)
        for name in self.bucket_names.values():
            (self.root / name).mkdir(parents=True, exist_ok=True)

    # -- env wiring -------------------------------------------------------

    def env(self) -> dict:
        """Return the environment overrides that point the code at this mount."""
        overrides = {"BUCKET_MOUNT_POINT": str(self.root)}
        overrides.update(self.bucket_names)
        return overrides

    def question_bank_dir(self) -> Path:
        """Path to the question-bank bucket directory."""
        return self.root / self.bucket_names["QUESTION_BANK_BUCKET"]

    # -- seeding inputs ---------------------------------------------------

    def seed_questions(self, source: str, rows: list) -> Path:
        """Write ``<source>_questions.jsonl`` into the question bank."""
        return self._write_jsonl(self.question_bank_dir() / f"{source}_questions.jsonl", rows)

    def seed_fetch(self, source: str, rows: list) -> Path:
        """Write ``<source>_fetch.jsonl`` into the question bank."""
        return self._write_jsonl(self.question_bank_dir() / f"{source}_fetch.jsonl", rows)

    def seed_resolution_file(self, source: str, question_id: str, rows: list) -> Path:
        """Write a per-question ``<source>/<id>.jsonl`` resolution file."""
        path = self.question_bank_dir() / source / f"{question_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return self._write_jsonl(path, rows)

    def seed_json(self, bucket_env_var: str, filename: str, payload) -> Path:
        """Write an arbitrary JSON file into the named bucket (e.g. a question set)."""
        path = self.root / self.bucket_names[bucket_env_var] / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    # -- reading outputs --------------------------------------------------

    def read_questions(self, source: str) -> pd.DataFrame:
        """Read back ``<source>_questions.jsonl`` produced by an update job."""
        return self._read_jsonl(self.question_bank_dir() / f"{source}_questions.jsonl")

    def read_fetch(self, source: str) -> pd.DataFrame:
        """Read back ``<source>_fetch.jsonl`` produced by a fetch job."""
        return self._read_jsonl(self.question_bank_dir() / f"{source}_fetch.jsonl")

    def read_resolution_file(self, source: str, question_id: str) -> pd.DataFrame:
        """Read back a per-question ``<source>/<id>.jsonl`` resolution file."""
        return self._read_jsonl(self.question_bank_dir() / source / f"{question_id}.jsonl")

    def list_resolution_ids(self, source: str) -> set:
        """Return the bare IDs that have a resolution file under ``<source>/``."""
        src_dir = self.question_bank_dir() / source
        if not src_dir.exists():
            return set()
        return {p.stem for p in src_dir.glob("*.jsonl")}

    # -- internals --------------------------------------------------------

    @staticmethod
    def _write_jsonl(path: Path, rows: list) -> Path:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    @staticmethod
    def _read_jsonl(path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        return pd.read_json(path, lines=True, convert_dates=False)


def apply_env(monkeypatch, overrides: dict) -> None:
    """Apply env overrides via monkeypatch (env is read at call time post-Layer-0)."""
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    # Ensure storage's mount read sees the value immediately.
    os.environ["BUCKET_MOUNT_POINT"] = overrides["BUCKET_MOUNT_POINT"]
