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
import tempfile
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

    def env(self) -> dict[str, str]:
        """Return the environment overrides that point the code at this mount."""
        overrides = {"BUCKET_MOUNT_POINT": str(self.root)}
        overrides.update(self.bucket_names)
        return overrides

    def question_bank_dir(self) -> Path:
        """Path to the question-bank bucket directory."""
        return self.root / self.bucket_names["QUESTION_BANK_BUCKET"]

    # -- seeding inputs ---------------------------------------------------

    def seed_questions(self, source: str, rows: list[dict]) -> Path:
        """Write ``<source>_questions.jsonl`` into the question bank."""
        return self._write_jsonl(self.question_bank_dir() / f"{source}_questions.jsonl", rows)

    def seed_fetch(self, source: str, rows: list[dict]) -> Path:
        """Write ``<source>_fetch.jsonl`` into the question bank."""
        return self._write_jsonl(self.question_bank_dir() / f"{source}_fetch.jsonl", rows)

    def seed_metadata(self, rows: list[dict]) -> Path:
        """Write ``question_metadata.jsonl`` into the question bank.

        Seed this (even empty) before running a metadata job: the job reads via the hardcoded
        ``/tmp/question_metadata.jsonl``, and ``download_and_read`` leaves that stale local file in
        place on a 404 — so a clean bucket copy is what makes the run start from known state.
        """
        return self._write_jsonl(self.question_bank_dir() / "question_metadata.jsonl", rows)

    def seed_resolution_file(self, source: str, question_id: str, rows: list[dict]) -> Path:
        """Write a per-question ``<source>/<id>.jsonl`` resolution file."""
        path = self.question_bank_dir() / source / f"{question_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return self._write_jsonl(path, rows)

    def seed_json(self, bucket_env_var: str, filename: str, payload: object) -> Path:
        """Write an arbitrary JSON file into the named bucket (e.g. a question set)."""
        path = self.root / self.bucket_names[bucket_env_var] / filename
        self._atomic_write_text(path, json.dumps(payload))
        return path

    def seed_forecast_set(self, date: str, filename: str, payload: object) -> Path:
        """Write a raw forecast set at ``FORECAST_SETS_BUCKET/<date>/<filename>``.

        ``func_resolve`` lists the bucket and groups by the leading ``<date>`` folder, so the
        date prefix is what makes the file discoverable.
        """
        return self.seed_json("FORECAST_SETS_BUCKET", f"{date}/{filename}", payload)

    def seed_question_set(self, filename: str, payload: object) -> Path:
        """Write a question set at ``QUESTION_SETS_BUCKET/<filename>`` (e.g. ``<date>-llm.json``)."""
        return self.seed_json("QUESTION_SETS_BUCKET", filename, payload)

    def seed_processed_forecast_set(self, date: str, filename: str, payload: object) -> Path:
        """Write a processed forecast set at ``PROCESSED_FORECAST_SETS_BUCKET/<date>/<filename>``."""
        return self.seed_json("PROCESSED_FORECAST_SETS_BUCKET", f"{date}/{filename}", payload)

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

    def list_resolution_ids(self, source: str) -> set[str]:
        """Return the bare IDs that have a resolution file under ``<source>/``."""
        src_dir = self.question_bank_dir() / source
        if not src_dir.exists():
            return set()
        return {p.stem for p in src_dir.glob("*.jsonl")}

    def read_json(self, bucket_env_var: str, filename: str) -> object:
        """Read back a JSON file from the named bucket."""
        path = self.root / self.bucket_names[bucket_env_var] / filename
        return json.loads(path.read_text(encoding="utf-8"))

    def read_processed_forecast_set(self, date: str, filename: str) -> object:
        """Read back a processed forecast set written by ``func_resolve``."""
        return self.read_json("PROCESSED_FORECAST_SETS_BUCKET", f"{date}/{filename}")

    def list_processed_forecast_files(self) -> set[str]:
        """Return ``<date>/<file>`` relpaths present in the processed-forecast-sets bucket."""
        root = self.root / self.bucket_names["PROCESSED_FORECAST_SETS_BUCKET"]
        return {str(p.relative_to(root)) for p in root.rglob("*.json")}

    # -- internals --------------------------------------------------------

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        """Write ``text`` to ``path`` atomically: temp file in the same dir, then ``os.replace``.

        A reader sees either the previous file or the complete new one, never a partial write, so an
        interrupted seed can't leave a torn JSON/JSONL file for a later read to misparse.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):  # only present if os.replace did not run (an error occurred)
                os.remove(tmp)

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict]) -> Path:
        text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        LocalBucket._atomic_write_text(path, text)
        return path

    @staticmethod
    def _read_jsonl(path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        return pd.read_json(path, lines=True, convert_dates=False)


def apply_env(monkeypatch, overrides: dict[str, str]) -> None:
    """Apply env overrides via monkeypatch (env is read at call time post-Layer-0)."""
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    # Ensure storage's mount read sees the value immediately.
    os.environ["BUCKET_MOUNT_POINT"] = overrides["BUCKET_MOUNT_POINT"]
