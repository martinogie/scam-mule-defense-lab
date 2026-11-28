"""One way to download real public data: guarded, recorded, cached, never half-written.

Every Phase 1 downloader (CFPB, FTC, IC3, FinCEN, Fed) calls `download()`. It:

1. Reuses a copy it already has, if that copy's fingerprint still matches (no network, so this is
   allowed even in a quiet window).
2. Otherwise refuses to start in a quiet window (`scamsim.schedule_guard`), with a polite
   `QuietWindowError` that says when to try again.
3. Saves the file as `data/raw/<source>/<YYYY-MM-DD>/<filename>` (UTC date of the download).
   `data/` is git-ignored: raw data never goes into the repository.
4. Writes a receipt next to it, `<filename>.source.json`: where it came from, when, its SHA-256
   fingerprint, its size and its licence. Every number in the project can be traced to one.
5. Downloads into a `.part` file first and renames it only when complete, so a broken connection
   never leaves a file that looks finished.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from scamsim.schedule_guard import ensure_not_quiet

DATA_DIR = Path("data")
CHUNK_BYTES = 1024 * 1024
TIMEOUT_SECONDS = 120
# A plain, generic name: requests to public sites carry nothing that identifies the project owner.
USER_AGENT = "public-data-downloader/1.0"
RECEIPT_SUFFIX = ".source.json"

# Source names become folder names, so only simple names are allowed ("cfpb", "fed-payments").
_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# File names: letters, digits, dots, dashes, underscores; no folders, no "..".
_SAFE_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

Fetch = Callable[[str], Iterable[bytes]]


@dataclass(frozen=True)
class SourceRecord:
    """The receipt for one downloaded file."""

    source: str
    url: str
    file: str  # path relative to the data folder, with forward slashes
    sha256: str
    size_bytes: int
    licence: str
    retrieved_at: str  # ISO 8601, UTC

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> SourceRecord:
        return cls(**json.loads(text))


def https_chunks(url: str, allowed_schemes: tuple[str, ...] = ("https",)) -> Iterator[bytes]:
    """Stream a file from the internet in 1 MB pieces (only https:// by default)."""
    scheme = urlparse(url).scheme
    if scheme not in allowed_schemes:
        raise ValueError(f"refusing {scheme or 'no'} scheme in {url!r}; only {allowed_schemes}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - scheme checked above
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        while chunk := response.read(CHUNK_BYTES):
            yield chunk


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def receipt_path(file_path: Path) -> Path:
    return file_path.with_name(file_path.name + RECEIPT_SUFFIX)


def find_cached(
    source: str, url: str, filename: str, data_dir: Path = DATA_DIR
) -> SourceRecord | None:
    """The newest earlier download of this exact URL whose file is intact, if there is one."""
    folder = data_dir / "raw" / source
    for receipt in sorted(folder.glob(f"*/{filename}{RECEIPT_SUFFIX}"), reverse=True):
        record = SourceRecord.from_json(receipt.read_text(encoding="utf-8"))
        file_path = data_dir / record.file
        if record.url != url or not file_path.is_file():
            continue
        if sha256_of(file_path) == record.sha256:
            return record
        # The file changed or got damaged since it was downloaded: don't trust it.
    return None


def download(
    source: str,
    url: str,
    filename: str,
    licence: str,
    *,
    data_dir: Path = DATA_DIR,
    refresh: bool = False,
    now: datetime | None = None,
    fetch: Fetch = https_chunks,
) -> SourceRecord:
    """Download `url` once, record where it came from, and return its receipt.

    `refresh=True` downloads again even if an intact copy exists (for sources that update).
    Raises `QuietWindowError` (polite, nothing changed) if a download is needed in a quiet window.
    """
    if not _SAFE_NAME.fullmatch(source):
        raise ValueError(f"source name {source!r} must be lower-case letters, digits, - or _")
    if not _SAFE_FILE.fullmatch(filename) or ".." in filename:
        raise ValueError(f"file name {filename!r} must be a plain name with no folders")
    if not licence.strip():
        raise ValueError("every download needs its licence written down")

    if not refresh and (cached := find_cached(source, url, filename, data_dir)) is not None:
        return cached

    now = now or datetime.now(UTC)
    ensure_not_quiet(f"Download of {source}/{filename}", now)

    folder = data_dir / "raw" / source / now.astimezone(UTC).strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / filename
    partial = final.with_name(final.name + ".part")

    digest, size = hashlib.sha256(), 0
    try:
        with partial.open("wb") as out:
            for chunk in fetch(url):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        os.replace(partial, final)  # only a complete file ever gets the real name
    finally:
        partial.unlink(missing_ok=True)

    record = SourceRecord(
        source=source,
        url=url,
        file=final.relative_to(data_dir).as_posix(),
        sha256=digest.hexdigest(),
        size_bytes=size,
        licence=licence.strip(),
        retrieved_at=now.astimezone(UTC).isoformat(timespec="seconds"),
    )
    receipt = receipt_path(final)
    receipt_tmp = receipt.with_name(receipt.name + ".part")
    receipt_tmp.write_text(record.to_json(), encoding="utf-8")
    os.replace(receipt_tmp, receipt)
    return record
