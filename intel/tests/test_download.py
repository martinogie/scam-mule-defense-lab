"""The download helper: guarded, recorded, cached, never half-written. Runs fully offline."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from intel.download import (
    SourceRecord,
    download,
    find_cached,
    https_chunks,
    receipt_path,
    sha256_of,
)
from scamsim.schedule_guard import CHICAGO, QuietWindowError

URL = "https://example.org/data/complaints.csv"
LICENCE = "Public domain (US government work)"
TUESDAY = datetime(2026, 12, 1, 9, 0, tzinfo=CHICAGO)  # outside every quiet window
MONDAY_MORNING = datetime(2026, 11, 30, 9, 0, tzinfo=CHICAGO)  # Bank Health's window


class FakeInternet:
    """Stands in for the network: serves fixed bytes and counts how often it was asked."""

    def __init__(self, body: bytes = b"id,story\n1,hello\n") -> None:
        self.body = body
        self.calls: list[str] = []

    def __call__(self, url: str) -> Iterator[bytes]:
        self.calls.append(url)
        yield self.body[:5]
        yield self.body[5:]


def test_downloads_into_dated_folder_with_a_receipt(tmp_path: Path) -> None:
    net = FakeInternet()
    record = download(
        "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net
    )

    saved = tmp_path / "raw" / "cfpb" / "2026-12-01" / "complaints.csv"
    assert saved.read_bytes() == net.body
    assert record.file == "raw/cfpb/2026-12-01/complaints.csv"
    assert record.sha256 == hashlib.sha256(net.body).hexdigest()
    assert record.size_bytes == len(net.body)
    assert record.licence == LICENCE
    assert record.url == URL
    assert record.retrieved_at == "2026-12-01T15:00:00+00:00"  # 09:00 Chicago = 15:00 UTC
    # The receipt on disk says the same thing.
    assert SourceRecord.from_json(receipt_path(saved).read_text(encoding="utf-8")) == record


def test_second_call_reuses_the_intact_copy(tmp_path: Path) -> None:
    net = FakeInternet()
    first = download(
        "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net
    )
    again = download(
        "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net
    )
    assert again == first
    assert len(net.calls) == 1  # the network was used once


def test_refresh_downloads_again(tmp_path: Path) -> None:
    net = FakeInternet()
    download("cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net)
    download(
        "cfpb",
        URL,
        "complaints.csv",
        LICENCE,
        data_dir=tmp_path,
        now=TUESDAY,
        fetch=net,
        refresh=True,
    )
    assert len(net.calls) == 2


def test_a_damaged_copy_is_not_trusted(tmp_path: Path) -> None:
    net = FakeInternet()
    record = download(
        "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net
    )
    (tmp_path / record.file).write_bytes(b"tampered")
    assert find_cached("cfpb", URL, "complaints.csv", tmp_path) is None
    fresh = download(
        "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net
    )
    assert len(net.calls) == 2
    assert sha256_of(tmp_path / fresh.file) == fresh.sha256


def test_a_different_url_is_a_different_download(tmp_path: Path) -> None:
    net = FakeInternet()
    download("cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net)
    other = URL.replace("complaints", "complaints-2025")
    download("cfpb", other, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net)
    assert net.calls == [URL, other]


def test_the_newest_intact_copy_wins(tmp_path: Path) -> None:
    net = FakeInternet()
    download("cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net)
    thursday = datetime(2026, 12, 3, 9, 0, tzinfo=CHICAGO)
    newer = download(
        "cfpb",
        URL,
        "complaints.csv",
        LICENCE,
        data_dir=tmp_path,
        now=thursday,
        fetch=net,
        refresh=True,
    )
    assert find_cached("cfpb", URL, "complaints.csv", tmp_path) == newer


def test_quiet_window_stops_a_download_politely(tmp_path: Path) -> None:
    net = FakeInternet()
    with pytest.raises(QuietWindowError, match="Bank Health"):
        download(
            "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=MONDAY_MORNING, fetch=net
        )
    assert net.calls == []  # nothing was fetched
    assert not (tmp_path / "raw").exists()  # nothing was written


def test_quiet_window_still_allows_a_cached_copy(tmp_path: Path) -> None:
    """Reading a file already on disk isn't heavy work, so it's fine during a quiet window."""
    net = FakeInternet()
    first = download(
        "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=TUESDAY, fetch=net
    )
    cached = download(
        "cfpb", URL, "complaints.csv", LICENCE, data_dir=tmp_path, now=MONDAY_MORNING, fetch=net
    )
    assert cached == first
    assert len(net.calls) == 1


def test_a_broken_connection_leaves_nothing_behind(tmp_path: Path) -> None:
    def drops_halfway(url: str) -> Iterator[bytes]:
        yield b"id,story\n"
        raise ConnectionError("connection reset")

    with pytest.raises(ConnectionError):
        download(
            "cfpb",
            URL,
            "complaints.csv",
            LICENCE,
            data_dir=tmp_path,
            now=TUESDAY,
            fetch=drops_halfway,
        )
    folder = tmp_path / "raw" / "cfpb" / "2026-12-01"
    assert list(folder.iterdir()) == []  # no file, no .part, no receipt


@pytest.mark.parametrize(
    ("source", "filename", "licence"),
    [
        ("CFPB", "complaints.csv", LICENCE),  # upper case source
        ("../etc", "complaints.csv", LICENCE),  # escapes the data folder
        ("cfpb", "../complaints.csv", LICENCE),
        ("cfpb", "sub/complaints.csv", LICENCE),
        ("cfpb", "complaints..csv", LICENCE),
        ("cfpb", "complaints.csv", "   "),  # no licence written down
    ],
)
def test_unsafe_names_and_missing_licences_are_refused(
    tmp_path: Path, source: str, filename: str, licence: str
) -> None:
    with pytest.raises(ValueError, match=r"source name|file name|licence"):
        download(
            source, URL, filename, licence, data_dir=tmp_path, now=TUESDAY, fetch=FakeInternet()
        )


def test_https_chunks_refuses_anything_but_https() -> None:
    with pytest.raises(ValueError, match="refusing http scheme"):
        next(https_chunks("http://example.org/file.csv"))
    with pytest.raises(ValueError, match="refusing file scheme"):
        next(https_chunks("file:///etc/passwd"))


def test_https_chunks_streams_a_real_file(tmp_path: Path) -> None:
    """Exercise the real urllib code path without the internet, via a local file:// URL."""
    source = tmp_path / "big.bin"
    body = bytes(range(256)) * 9000  # about 2.3 MB: more than one 1 MB chunk
    source.write_bytes(body)
    chunks = list(https_chunks(source.as_uri(), allowed_schemes=("file",)))
    assert len(chunks) == 3
    assert b"".join(chunks) == body
