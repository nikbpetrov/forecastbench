"""Post-install patch for the pinned ``fri-utils`` package's ``gcp/storage.py``.

``main`` consumes ``utils`` as a pinned pip dependency (``fri-utils`` in
``requirements.runtime.txt``), not a git submodule. That pinned build routes only ``list()`` /
``get_last_modified_time()`` to a local ``BUCKET_MOUNT_POINT`` mount; ``download()`` / ``upload()``
/ ``list_with_prefix()`` / ``file_exists()`` always hit real GCS. The offline test framework needs
*all* of them to honor the mount so tests run with no network/GCP.

This script applies that routing to the installed package in place (the equivalent of an npm
``postinstall`` patch). It is:

* **Idempotent** — re-running is a no-op once patched (detected by the ``_mount`` sentinel).
* **Version-guarded** — it only patches the exact pinned build it knows about (fingerprinted by
  the unpatched function bodies). If the ``fri-utils`` pin changes and the file no longer matches,
  it prints a loud warning and does nothing, so a future upgrade is never silently clobbered.

The routing is gated on ``BUCKET_MOUNT_POINT`` being set and the mount dir existing, so the patched
build behaves identically to the upstream build in production (where the var is unset or points at
the real mount).

Run via ``make setup-python-env`` (wired into the Makefile) or directly: ``python
scripts/patch_fri_utils.py``.
"""

import sys

# The routing-enabled replacement for ``utils/gcp/storage.py``. Tracks the pinned build
# (fri-utils @ 7d9479c): same public API, with call-time ``_mount()`` + local routing added to
# every IO function. Keep in sync if the pin in requirements.runtime.txt changes.
PATCHED_STORAGE = '''"""Simplify Cloud Storage interactions.

Patched in place by ``scripts/patch_fri_utils.py``: every IO function honors a local
``BUCKET_MOUNT_POINT`` mount (read at call time) so the offline test suite needs no network/GCS.
Behavior is unchanged when the mount is unset (production).
"""

import os
import pathlib
import shutil
from datetime import datetime, timezone
from typing import List, Optional

from google.cloud import storage

from . import (
    storage_download_file,
    storage_list_files,
    storage_list_files_with_prefix,
    storage_upload_file,
)


def _mount() -> str:
    """Return the bucket mount point, read from the environment at call time."""
    return os.environ.get("BUCKET_MOUNT_POINT", "")


def list_with_prefix(
    bucket_name: str,
    prefix: str,
    mnt: str = None,
):
    """List files in the folder specified by `prefix`."""
    mnt = _mount() if mnt is None else mnt
    mount_dir = f"{mnt}/{bucket_name}"
    if mnt and os.path.exists(mount_dir):
        results = []
        prefix_dir = os.path.join(mount_dir, prefix)
        if os.path.exists(prefix_dir):
            for root, _, files in os.walk(prefix_dir):
                for f in files:
                    full_path = os.path.join(root, f)
                    results.append(os.path.relpath(full_path, mount_dir))
        return results

    return storage_list_files_with_prefix.list_blobs_with_prefix(
        bucket_name=bucket_name,
        prefix=prefix,
    )


def file_exists(bucket_name: str, filename: str) -> bool:
    """Return True if an object with this exact name exists in the bucket."""
    mnt = _mount()
    if mnt and os.path.exists(f"{mnt}/{bucket_name}"):
        return os.path.exists(f"{mnt}/{bucket_name}/{filename}")
    storage_client = storage.Client()
    return storage_client.bucket(bucket_name).blob(filename).exists()


def list(
    bucket_name: str,
    mnt: str = None,
) -> List[str]:
    """List files in the bucket.

    Args:
        bucket_name (str): name of bucket.
        mnt (str): mount dir of bucket.

    Returns:
        List[str]: list of files in bucket.
    """
    mnt = _mount() if mnt is None else mnt
    mount_dir = f"{mnt}/{bucket_name}"
    if mnt and os.path.exists(mount_dir):
        retval = []
        for root, _, files in os.walk(mount_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, mount_dir)
                retval.append(rel_path)
        return retval

    return storage_list_files.list_blobs(
        bucket_name=bucket_name,
    )


def upload(
    bucket_name: str,
    local_filename: str,
    destination_folder: str = "",
    *,
    filename: str = None,
    mnt: str = None,
):
    """Facilitate uploading file to cloud storage."""
    mnt = _mount() if mnt is None else mnt
    if not filename:
        filename = os.path.basename(local_filename)
    destination_filename = f"{destination_folder}/{filename}" if destination_folder else filename

    mount_dir = f"{mnt}/{bucket_name}"
    if mnt and os.path.exists(mount_dir):
        dest = os.path.join(mount_dir, destination_filename)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(local_filename, dest)
        return

    storage_upload_file.upload_blob(
        bucket_name,
        local_filename,
        destination_filename,
    )


def download(
    bucket_name: str,
    filename: str,
    local_filename: str = None,
    mnt: str = None,
) -> str:
    """Facilitate downloading file from cloud storage."""
    mnt = _mount() if mnt is None else mnt
    if not local_filename:
        directory, basename = os.path.split(filename)
        local_directory = f"/tmp/{directory}"
        pathlib.Path(local_directory).mkdir(parents=True, exist_ok=True)
        local_filename = f"{local_directory}/{basename}"

    mount_dir = f"{mnt}/{bucket_name}"
    source_path = f"{mount_dir}/{filename}"
    if mnt and os.path.exists(source_path):
        shutil.copy2(source_path, local_filename)
        return local_filename

    storage_download_file.download_blob(bucket_name, filename, local_filename)

    return local_filename


def download_no_error_message_on_404(
    bucket_name: str,
    filename: str,
    local_filename: str = None,
    mnt: str = None,
) -> str:
    """Wrap `download()` function that doesn't print "Error" message if requested file not found."""
    try:
        local_filename = download(
            bucket_name=bucket_name,
            filename=filename,
            local_filename=local_filename,
            mnt=mnt,
        )
    except Exception:
        print(f"GCP Storage: could not download {bucket_name}/{filename}.")

    return local_filename


def get_last_modified_time(
    bucket_name: str,
    filename: str,
    mnt: str = None,
) -> Optional[datetime]:
    """Return the last modified date for the given file."""
    mnt = _mount() if mnt is None else mnt
    mount_dir = f"{mnt}/{bucket_name}"
    if mnt and os.path.exists(mount_dir):
        ts = os.path.getmtime(f"{mount_dir}/{filename}")
        return datetime.fromtimestamp(ts, tz=timezone.utc)

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.get_blob(filename)
        return blob.updated if blob else None
    except Exception:
        print(f"GCP Storage: could not find modified time of {bucket_name}/{filename}.")
        return None
'''

# Fingerprints of the exact unpatched pinned build we know how to patch. If any is absent, the
# installed file is not the expected version -> warn and skip (never clobber an unknown build).
_FINGERPRINTS = (
    "def file_exists(bucket_name: str, filename: str) -> bool:",
    "storage_download_file.download_blob(bucket_name, filename, local_filename)",
    "from . import (",
)
_ALREADY_PATCHED_SENTINEL = "def _mount() -> str:"


def _locate_storage() -> str:
    """Return the filesystem path of the installed ``utils.gcp.storage`` module."""
    from utils.gcp import storage as installed

    return installed.__file__


def main() -> int:
    """Patch the installed ``fri-utils`` storage module; return a process exit code."""
    try:
        path = _locate_storage()
    except Exception as exc:  # pragma: no cover - import failure is environment-specific
        print(f"[patch_fri_utils] could not import utils.gcp.storage: {exc}", file=sys.stderr)
        return 0  # don't break the build; the test run will surface a missing dependency

    with open(path, encoding="utf-8") as fh:
        current = fh.read()

    if _ALREADY_PATCHED_SENTINEL in current:
        print(f"[patch_fri_utils] already patched: {path}")
        return 0

    missing = [fp for fp in _FINGERPRINTS if fp not in current]
    if missing:
        print(
            "[patch_fri_utils] WARNING: installed fri-utils storage.py does not match the known "
            f"pinned build (missing fingerprints: {missing}). NOT patching {path}. If the "
            "fri-utils pin changed, update scripts/patch_fri_utils.py.",
            file=sys.stderr,
        )
        return 0

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(PATCHED_STORAGE)
    print(f"[patch_fri_utils] patched local-mount routing into {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
