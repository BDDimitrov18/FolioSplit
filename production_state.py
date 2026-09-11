"""Validated per-source publication and resume. No model or GPU imports."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from pypdf import PdfReader


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".json-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def state_key(pdf: Path) -> str:
    return hashlib.sha256(pdf.name.encode()).hexdigest()[:24]


def manifest_path(pdf: Path, output: Path) -> Path:
    return output / ".state" / (state_key(pdf) + ".json")


@contextmanager
def source_lock(pdf: Path, output: Path):
    """OS releases the lock after a crash; overlapping shards cannot publish together."""
    state = output / ".state"
    state.mkdir(parents=True, exist_ok=True)
    with (state / (state_key(pdf) + ".lock")).open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another worker is processing {pdf.name}") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def source_identity(pdf: Path) -> dict:
    return {"name": pdf.name, "sha256": file_hash(pdf), "bytes": pdf.stat().st_size}


def output_files(pdf: Path, output: Path) -> list[Path]:
    # Escape stems; glob metacharacters in input filenames are ordinary text.
    pattern = re.compile(re.escape(pdf.stem) + r"_\d{3,}_\d{5,}_.*\.pdf$", re.I)
    return sorted(p for p in output.iterdir() if p.is_file() and pattern.fullmatch(p.name))


def is_complete(pdf: Path, output: Path, source: dict, settings: dict) -> bool:
    """A filename's existence never proves completion; verify the published set."""
    try:
        record = json.loads(manifest_path(pdf, output).read_text(encoding="utf-8"))
        if (record["version"] != 1 or record["status"] != "complete"
                or record["source"] != source or record["settings"] != settings):
            return False
        segments = record["segments"]
        if (not segments or len({s["file"] for s in segments}) != len(segments)
                or {p.name for p in output_files(pdf, output)} != {s["file"] for s in segments}):
            return False
        next_page = 1
        for segment in segments:
            name = segment["file"]
            if Path(name).name != name or segment["start_page"] != next_page:
                return False
            path = output / name
            count = segment["end_page"] - segment["start_page"] + 1
            if (count <= 0 or file_hash(path) != segment["sha256"]
                    or len(PdfReader(str(path)).pages) != count):
                return False
            next_page = segment["end_page"] + 1
        return next_page == record["total_pages"] + 1 == len(PdfReader(str(pdf)).pages) + 1
    except Exception:
        # Includes unreadable manifests and pypdf-specific malformed-PDF exceptions.
        return False


def publish(pdf: Path, output: Path, source: dict, settings: dict, total: int,
            boundaries: list, rotations: dict, split_fn, logger, review_threshold: float = .8) -> dict:
    """Stage/validate all segments, publish, then write the completion marker LAST.

    A flat file set cannot be renamed atomically. The manifest is the commit marker:
    interruptions force validation/reprocessing. Prior outputs are kept in .history.
    Caller must hold source_lock across resume checking, inference and publication.
    """
    starts = [b.page for b in boundaries]
    if (total < 1 or not starts or starts[0] != 1 or starts != sorted(set(starts))
            or any(type(p) is not int or not 1 <= p <= total for p in starts)):
        raise ValueError("Boundaries must cover the source from page 1, in increasing order")
    output.mkdir(parents=True, exist_ok=True)
    if len(PdfReader(str(pdf)).pages) != total:
        raise ValueError("Declared source page count does not match the PDF")
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=output) as temp:
        staging = Path(temp)
        paths = [Path(p) for p in split_fn(pdf, boundaries, staging, logger)]
        if len(paths) != len(starts) or len(set(paths)) != len(paths):
            raise ValueError("Split output count does not match the document boundaries")
        segments = []
        for i, (boundary, path) in enumerate(zip(boundaries, paths)):
            if path.parent != staging or not path.is_file():
                raise ValueError("Split output must be inside the staging directory")
            end = starts[i + 1] - 1 if i + 1 < len(starts) else total
            if len(PdfReader(str(path)).pages) != end - boundary.page + 1:
                raise ValueError(f"Output page count mismatch: {path.name}")
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
            segments.append({**asdict(boundary), "file": path.name,
                             "start_page": boundary.page, "end_page": end,
                             "needs_review": boundary.page != 1 and boundary.confidence < review_threshold,
                             "sha256": file_hash(path)})
        if source_identity(pdf) != source:
            raise RuntimeError("Source changed while it was being processed")
        record = {"version": 1, "status": "complete", "source": source, "settings": settings,
                  "completed_at": datetime.now(timezone.utc).isoformat(), "total_pages": total,
                  "rotations_ccw_for_inference": rotations, "segments": segments}
        json.dumps(record, allow_nan=False)  # Validate before touching previous outputs.
        old = output_files(pdf, output)
        marker = manifest_path(pdf, output)
        if old or marker.exists():
            history = output / ".history" / state_key(pdf) / uuid.uuid4().hex
            history.mkdir(parents=True)
            if marker.exists():
                os.replace(marker, history / "completion.json")
            for path in old:
                os.replace(path, history / path.name)
        for path in paths:
            os.replace(path, output / path.name)
        atomic_json(marker, record)
        return record
