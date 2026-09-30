"""
Everything that touches the disk: JSON/JSONL, hashes, manifests, caches, downloads.

    from store import write_jsonl, read_jsonl, build_or_load, check_manifest

WHY A MODULE FOR THIS
---------------------
Every stage hands its output to the next through files, and the most common way to get
a wrong table in this lab is to read the wrong file without noticing: an index built from
last week's documents, a smoke index scored as if it were the full one, an eval set that
changed after the results were computed. Nothing errors -- the numbers are just about
something else. So every artifact here carries a MANIFEST (what built it, from what, with
which settings), and readers check it on load.

Public API:
    canonical_json, sha256_json, sha256_file, sha256_text,
    write_json, read_json, write_jsonl, read_jsonl, append_jsonl,
    ManifestMismatch, manifest_path, write_manifest, read_manifest, check_manifest,
    is_fresh, build_or_load, cached_matrix, TRANSIENT_ERRORS, ResultsLog,
    fetch_git, fetch_url, pack_for_review

Stdlib only, except `cached_matrix` (numpy) and `read_jsonl(model=...)` (pydantic).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


# --- hashing --------------------------------------------------------------------------------
def canonical_json(obj: Any) -> str:
    """One string per value: sorted keys, no whitespace, UTF-8 kept as is.

    Hashes are taken over THIS, never over file bytes, so re-saving a file in another
    editor (CRLF, trailing newline, key order) doesn't change what it "is".
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# --- JSON / JSONL -----------------------------------------------------------------------------
def _atomic_write_text(path: Path, text: str) -> None:
    """Write to a temp file in the same directory, then rename: a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_json(path: str | Path, obj: Any) -> None:
    _atomic_write_text(Path(path), json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n")


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump_row(row: Any) -> str:
    if hasattr(row, "model_dump"):  # a pydantic model
        row = row.model_dump(mode="json")
    return json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)


def write_jsonl(path: str | Path, rows: Iterable[Any]) -> int:
    """Write rows (dicts or pydantic models) as JSONL, atomically. Returns the row count."""
    lines = [_dump_row(r) for r in rows]
    _atomic_write_text(Path(path), "".join(line + "\n" for line in lines))
    return len(lines)


def read_jsonl(path: str | Path, model: type | None = None) -> list:
    """Read a JSONL file. With `model` (a pydantic class), validate and return instances.

    A torn LAST line (a crash mid-append) is skipped with a warning; a bad line anywhere
    else is a real corruption and raises.
    """
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        raw = f.read().split("\n")
    if raw and raw[-1] == "":
        raw.pop()
    rows = []
    for i, line in enumerate(raw):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            if i == len(raw) - 1:
                print(f"WARNING: {path.name}: skipping a torn last line ({e})", file=sys.stderr)
                break
            raise ValueError(f"{path.name}:{i + 1}: not valid JSON ({e})") from e
        rows.append(model.model_validate(obj) if model is not None else obj)
    return rows


def append_jsonl(path: str | Path, row: Any) -> None:
    """Append one row and flush it to disk (safe to interrupt; safe on a Drive mount).

    If a previous run died mid-append, the file ends in a torn line with no newline;
    read_jsonl skips it, but appending after it would glue the new row onto it and turn it
    into a corrupt line in the MIDDLE of the file. So a torn tail is cut off first.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (_dump_row(row) + "\n").encode("utf-8")
    with open(path, "a+b") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size:
            f.seek(size - 1)
            if f.read(1) != b"\n":
                f.seek(0)
                f.truncate(f.read().rfind(b"\n") + 1)
        f.seek(0, os.SEEK_END)
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


# --- manifests --------------------------------------------------------------------------------
class ManifestMismatch(RuntimeError):
    """An artifact was built from something other than what the reader expects."""


def manifest_path(artifact: str | Path) -> Path:
    artifact = Path(artifact)
    return artifact.with_name(artifact.name + ".manifest.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_manifest(artifact: str | Path, spec: dict, **extra: Any) -> dict:
    """Record what built `artifact` next to it, as `<artifact>.manifest.json`.

    `spec` is everything that DETERMINES the artifact's content (inputs' hashes, model ids
    and revisions, settings). Its hash is the artifact's `key`. `extra` is descriptive
    (counts, timings) and is not compared.
    """
    import environment  # late: keeps this module importable without environment's side effects

    artifact = Path(artifact)
    manifest = {
        "spec": spec,
        "key": sha256_json(spec),
        "created_at": _now(),
        "env": environment.versions(),
        **extra,
    }
    if artifact.is_file():
        manifest["sha256"] = sha256_file(artifact)
        manifest["bytes"] = artifact.stat().st_size
    write_json(manifest_path(artifact), manifest)
    return manifest


def read_manifest(artifact: str | Path) -> dict | None:
    path = manifest_path(artifact)
    return read_json(path) if path.is_file() else None


def _spec_diff(expected: dict, found: dict, prefix: str = "") -> list[str]:
    diffs = []
    for key in sorted(set(expected) | set(found)):
        e, f = expected.get(key, "<missing>"), found.get(key, "<missing>")
        if isinstance(e, dict) and isinstance(f, dict):
            diffs += _spec_diff(e, f, f"{prefix}{key}.")
        elif canonical_json(e) != canonical_json(f):
            diffs.append(f"  {prefix}{key}: expected {e!r}, found {f!r}")
    return diffs


def check_manifest(artifact: str | Path, spec: dict) -> dict:
    """Raise ManifestMismatch unless `artifact` was built from exactly `spec`.

    This is the load-time check: a stage that reads an index or a documents file calls it
    with the spec it expects, and a mismatch stops the stage instead of scoring the wrong thing.
    """
    artifact = Path(artifact)
    manifest = read_manifest(artifact)
    if manifest is None:
        raise ManifestMismatch(f"{artifact}: no manifest next to it -- rebuild it with its stage.")
    if manifest.get("key") != sha256_json(spec):
        raise ManifestMismatch(
            f"{artifact.name} was built from a different spec:\n"
            + "\n".join(_spec_diff(spec, manifest.get("spec", {})))
        )
    if artifact.is_file() and manifest.get("sha256") and manifest["sha256"] != sha256_file(artifact):
        raise ManifestMismatch(f"{artifact.name}: file content changed after its manifest was written.")
    return manifest


def is_fresh(artifact: str | Path, spec: dict) -> bool:
    """True if `artifact` exists and its manifest matches `spec` (no exception)."""
    if not Path(artifact).exists():
        return False
    try:
        check_manifest(artifact, spec)
    except ManifestMismatch:
        return False
    return True


def build_or_load(artifact: str | Path, spec: dict, build: Callable[[Path], Any],
                  *, force: bool = False, **extra: Any) -> Path:
    """Build `artifact` with `build(path)` unless an up-to-date copy is already on disk.

    This is what makes a disconnected Colab session cheap to resume: re-run the notebook
    from the top and every stage whose inputs didn't change prints `reusing` and moves on.
    """
    artifact = Path(artifact)
    if not force and is_fresh(artifact, spec):
        built = (read_manifest(artifact) or {}).get("created_at", "?")
        print(f"reusing {artifact.name} (built {built})")
        return artifact
    if artifact.exists() and not force:
        old = read_manifest(artifact)
        if old is not None:
            print(f"rebuilding {artifact.name}: its spec changed\n"
                  + "\n".join(_spec_diff(spec, old.get("spec", {}))))
    print(f"building {artifact.name} ...")
    build(artifact)
    if not artifact.exists():
        raise RuntimeError(f"build() returned without writing {artifact}")
    write_manifest(artifact, spec, **extra)
    return artifact


# --- embedding cache --------------------------------------------------------------------------
def cached_matrix(name: str, spec: dict, ids: list[str], texts: list[str],
                  encode: Callable[[list[str]], Any], *, art_dir: str | Path,
                  shard_rows: int = 4096):
    """Encode `texts` once and keep the matrix on disk, keyed by what produced it.

    `spec` must describe the ENCODER (model id, revision, max_seq_length, dtype, prefixes);
    the ids AND the texts are hashed in automatically, so a changed chunk (a new cleaning
    rule, a contextual prefix) is a different matrix even under the same ids. Shards are
    written as they finish, so a pass interrupted halfway resumes where it stopped.

    Returns a float32 numpy array with one row per text, in the order given.
    """
    import numpy as np

    if len(ids) != len(texts):
        raise ValueError(f"{len(ids)} ids but {len(texts)} texts")
    full_spec = {"encoder": spec, "ids_sha256": sha256_json(ids), "texts_sha256": sha256_json(texts),
                 "n": len(ids)}
    key = sha256_json(full_spec)[:16]
    folder = Path(art_dir) / "embeddings" / f"{name}-{key}"
    final = folder / "matrix.npy"
    if final.is_file() and is_fresh(final, full_spec):
        matrix = np.load(final)
        print(f"reusing embeddings {name} {matrix.shape} (key {key})")
        return matrix

    folder.mkdir(parents=True, exist_ok=True)
    parts = []
    n_shards = (len(texts) + shard_rows - 1) // shard_rows
    for s in range(n_shards):
        lo, hi = s * shard_rows, min((s + 1) * shard_rows, len(texts))
        # Named by row range: a resume with a different shard size can't reuse the wrong rows.
        shard = folder / f"rows_{lo:09d}_{hi:09d}.npy"
        if shard.is_file():
            try:
                part = np.load(shard)
                if part.shape[0] == hi - lo:
                    parts.append(part)
                    continue
            except (ValueError, OSError, EOFError):
                pass  # torn by an interruption: re-encode it
        part = np.asarray(encode(texts[lo:hi]), dtype=np.float32)
        if part.shape[0] != hi - lo:
            raise RuntimeError(f"encoder returned {part.shape[0]} rows for {hi - lo} texts")
        _atomic_save_npy(shard, part)
        parts.append(part)
        print(f"   embedded shard {s + 1}/{n_shards} ({hi}/{len(texts)} rows)")
    matrix = np.concatenate(parts, axis=0) if parts else np.zeros((0, 0), dtype=np.float32)
    _atomic_save_npy(final, matrix)
    write_manifest(final, full_spec, shape=list(matrix.shape))
    for f in folder.glob("rows_*.npy"):
        f.unlink(missing_ok=True)
    return matrix


def _atomic_save_npy(path: Path, array) -> None:
    import numpy as np

    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        np.save(f, array)
    os.replace(tmp, path)


# --- resumable results ------------------------------------------------------------------------
# A row whose error starts with one of these didn't produce a result -- the server was down,
# the connection dropped -- so a resumed run retries it instead of treating it as done.
# PARSE_FAILED, SILENT_TRUNCATION, CONTEXT_OVERFLOW are results: they stay done.
TRANSIENT_ERRORS = ("ConnectionError", "ConnectTimeout", "ReadTimeout", "ChunkedEncodingError",
                    "LLMError: HTTP 5")


def _settled(row: dict) -> bool:
    return not str(row.get("error") or "").startswith(TRANSIENT_ERRORS)


class ResultsLog:
    """Per-item results for one experiment, appended as they're computed.

        ev = schema.load_eval("eval", documents_path=ART / "documents.jsonl")
        log = ResultsLog(ART / "results" / "03_retrieval.jsonl",
                         run_spec={"config": {...}, "eval": ev.key()})
        for arm in ARMS:
            for item in items:
                if log.done(arm, item.item_id):
                    continue
                log.write({"arm": arm, "item_id": item.item_id, "metrics": {...}})

    Rows carry the hash of `run_spec` (`config_key`); rows written under a different spec
    are ignored, never mixed in -- so put in `run_spec` everything a row's meaning depends
    on, the eval-set hash included. A failed item is still a row, with `error` set, so a
    table can say "3 of 60 failed" instead of silently averaging the other 57. Rows that
    failed for transient reasons (TRANSIENT_ERRORS) are retried on resume; when an item has
    several rows, the last one wins.
    """

    def __init__(self, path: str | Path, run_spec: dict):
        self.path = Path(path)
        self.run_spec = run_spec
        self.config_key = sha256_json(run_spec)[:16]
        self._done: set[tuple[str, str]] = set()
        self._rows: list[dict] = []
        if self.path.is_file():
            for row in read_jsonl(self.path):
                if row.get("config_key") == self.config_key:
                    self._rows.append(row)
                    if _settled(row):
                        self._done.add((str(row.get("arm")), str(row.get("item_id"))))
        # One small file per spec: no read-modify-write that two notebooks could race on.
        spec_file = self.path.with_name(f"{self.path.stem}.config-{self.config_key}.json")
        if not spec_file.is_file():
            write_json(spec_file, {"spec": run_spec, "first_seen": _now()})
        if self._rows:
            print(f"{self.path.name}: resuming, {len(self._done)} items already done "
                  f"under config {self.config_key}")

    def done(self, arm: str, item_id: str) -> bool:
        return (str(arm), str(item_id)) in self._done

    def write(self, row: dict) -> None:
        if "arm" not in row or "item_id" not in row:
            raise ValueError("a results row needs 'arm' and 'item_id'")
        row = {**row, "config_key": self.config_key}
        append_jsonl(self.path, row)
        self._rows.append(row)
        if _settled(row):
            self._done.add((str(row["arm"]), str(row["item_id"])))

    def rows(self, arm: str | None = None) -> list[dict]:
        """One row per (arm, item): the latest one written."""
        latest: dict[tuple[str, str], dict] = {}
        for r in self._rows:
            if arm is None or str(r.get("arm")) == str(arm):
                latest[(str(r.get("arm")), str(r.get("item_id")))] = r
        return list(latest.values())


# --- downloads ---------------------------------------------------------------------------------
def _git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def fetch_git(url: str, dest: str | Path, *, commit: str, branch: str | None = None) -> str:
    """Check out exactly `commit` of `url` into `dest` (shallow), and return HEAD.

    Pinning a commit, not a branch, is what makes "the corpus" mean the same thing next
    month. If `dest` is already at `commit`, nothing is downloaded. Submodules are never
    fetched. Line endings are never converted (Git for Windows converts to CRLF by
    default, which would make the same commit hash differently on a laptop and on Colab).
    """
    dest = Path(dest)
    if (dest / ".git").is_dir():
        try:
            head = _git("rev-parse", "HEAD", cwd=dest)
            if head.startswith(commit) or commit.startswith(head):
                print(f"reusing {dest.name} @ {head[:12]}")
                return head
        except RuntimeError:
            pass
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").is_dir():
        _git("init", "-q", cwd=dest)
        _git("remote", "add", "origin", url, cwd=dest)
    else:
        try:
            _git("remote", "set-url", "origin", url, cwd=dest)  # the pin may point at a new URL
        except RuntimeError:
            _git("remote", "add", "origin", url, cwd=dest)
    _git("config", "core.autocrlf", "false", cwd=dest)
    _git("config", "core.eol", "lf", cwd=dest)
    try:
        _git("fetch", "-q", "--depth", "1", "origin", commit, cwd=dest)
        target = "FETCH_HEAD"
    except RuntimeError:
        if not branch:
            raise
        # Some servers refuse fetch-by-SHA, and none accepts a SHORT one: fetch the branch
        # and resolve `commit` locally, where abbreviations work.
        _git("fetch", "-q", "--depth", "50", "origin", branch, cwd=dest)
        target = commit
    _git("checkout", "-q", "--detach", target, cwd=dest)
    head = _git("rev-parse", "HEAD", cwd=dest)
    if not (head.startswith(commit) or commit.startswith(head)):
        raise RuntimeError(f"{url}: asked for {commit}, got {head}")
    print(f"fetched {url} @ {head[:12]} -> {dest}")
    return head


def fetch_url(url: str, dest: str | Path, *, sha256: str | None = None,
              on_mismatch: str = "raise", timeout: int = 60) -> tuple[Path, str]:
    """Download `url` to `dest` (resumable), and return (path, sha256).

    With `sha256` given, a different file raises (`on_mismatch="raise"`) or is kept with a
    loud warning (`"warn"`) -- for sources that are rebuilt in place, where the honest move
    is to record the new hash in your manifest rather than to pretend nothing changed. With
    "warn", a file already on disk is REUSED even if it differs from the pin: your corpus
    must not silently follow upstream between one stage and the next. Delete it to refetch.

    An interrupted download resumes only if the server confirms the file hasn't changed
    since (If-Range); otherwise it starts over, instead of splicing two versions together.
    """
    import requests

    dest = Path(dest)
    if dest.is_file():
        digest = sha256_file(dest)
        if sha256 is None or digest == sha256:
            print(f"reusing {dest.name} ({dest.stat().st_size:,} bytes)")
            return dest, digest
        if on_mismatch == "warn":
            print(f"WARNING: reusing {dest.name} (sha256 {digest[:16]}...), which is NOT the pinned "
                  f"{sha256[:16]}...; delete it to fetch the current upstream build.", file=sys.stderr)
            return dest, digest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    meta = dest.with_name(dest.name + ".part.json")
    done = part.stat().st_size if part.is_file() else 0
    validator = (read_json(meta) if meta.is_file() else {}).get("validator") if done else None
    if done and not validator:
        done = 0  # nothing proves the bytes on disk belong to the current file
    headers = {"Accept-Encoding": "identity"}  # ranges are counted in raw bytes
    if done:
        headers.update({"Range": f"bytes={done}-", "If-Range": validator})
    with requests.get(url, stream=True, timeout=timeout, headers=headers) as r:
        if r.status_code == 416:
            if r.headers.get("Content-Range") != f"bytes */{done}":
                # The partial is longer than the file now is: it belongs to another build.
                part.unlink(missing_ok=True)
                meta.unlink(missing_ok=True)
                return fetch_url(url, dest, sha256=sha256, on_mismatch=on_mismatch, timeout=timeout)
            # else: the .part is already the complete file
        else:
            r.raise_for_status()
            _stream_to(r, part, "ab" if done and r.status_code == 206 else "wb", meta)
    os.replace(part, dest)
    meta.unlink(missing_ok=True)
    digest = sha256_file(dest)
    if sha256 is not None and digest != sha256:
        message = (f"{dest.name}: sha256 {digest[:16]}... differs from the pinned {sha256[:16]}... "
                   "-- the source changed since it was pinned")
        if on_mismatch == "raise":
            raise RuntimeError(message)
        print("WARNING: " + message, file=sys.stderr)
    print(f"downloaded {dest.name} ({dest.stat().st_size:,} bytes, sha256 {digest[:12]})")
    return dest, digest


def _stream_to(response, part: Path, mode: str, meta: Path) -> None:
    if mode == "wb":
        write_json(meta, {"validator": response.headers.get("ETag") or response.headers.get("Last-Modified")})
    with open(part, mode) as f:
        for block in response.raw.stream(1 << 20, decode_content=False):
            f.write(block)


# --- packing results for review --------------------------------------------------------------------
_PACK_SKIP_DIRS = ("embeddings", "bm25", "llm_cache", "logs")   # a directory whose NAME starts with one
_PACK_SKIP_FILES = {"documents.jsonl", "chunks.jsonl", "parents.jsonl"}   # rebuilt from the corpus


def pack_for_review(art_dir: str | Path, out: str | Path | None = None,
                    max_file_mb: float = 50.0) -> Path:
    """Zip the `artifacts/<profile>/` part of a submission, without the heavy caches.

    Keeps results, memory stores, manifests and the run report; skips, at any depth,
    embeddings, BM25 indexes (`bm25/`, `bm25_raw/`, ...), LLM caches and logs, the corpus
    files a stage rebuilds (`documents.jsonl`, `chunks.jsonl`, `parents.jsonl` -- their
    manifests stay, and they say which corpus it was), and any single file over `max_file_mb`.
    Your `eval/`, `corpus_card.md` and `decision_log.md` live in the repo, not here: add
    them to the submission yourself.
    """
    art_dir = Path(art_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = Path(out) if out else art_dir / f"review_{stamp}.zip"
    kept, skipped = 0, []
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(art_dir.rglob("*")):
            rel = path.relative_to(art_dir)
            if not path.is_file() or path == out or path.suffix == ".zip":
                continue
            if any(part.startswith(_PACK_SKIP_DIRS) for part in rel.parts[:-1]) or path.name in _PACK_SKIP_FILES:
                continue
            if path.stat().st_size > max_file_mb * 1e6:
                skipped.append(f"{rel} ({path.stat().st_size / 1e6:.0f} MB)")
                continue
            z.write(path, rel.as_posix())
            kept += 1
    print(f"packed {kept} files into {out}")
    if skipped:
        print("skipped (too large): " + ", ".join(skipped))
    return out


# --- self-test -------------------------------------------------------------------------------------
def _selftest() -> None:
    root = Path(tempfile.mkdtemp(prefix="store_selftest_"))
    try:
        rows = [{"b": 2, "a": "ñandú"}, {"a": "x", "b": 1}]
        assert write_jsonl(root / "x.jsonl", rows) == 2
        assert read_jsonl(root / "x.jsonl") == rows
        with open(root / "x.jsonl", "a", encoding="utf-8") as f:
            f.write('{"torn": ')
        assert read_jsonl(root / "x.jsonl") == rows, "torn last line must be skipped"
        assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})

        target = root / "doc.txt"
        spec = {"source": "abc", "n": 3}
        calls = []
        build = lambda p: (calls.append(1), p.write_text("hello", encoding="utf-8"))
        build_or_load(target, spec, build)
        build_or_load(target, spec, build)
        assert len(calls) == 1, "second call must reuse"
        check_manifest(target, spec)
        try:
            check_manifest(target, {"source": "abc", "n": 4})
        except ManifestMismatch:
            pass
        else:
            raise AssertionError("a different spec must raise")
        build_or_load(target, {"source": "abc", "n": 4}, build)
        assert len(calls) == 2, "a changed spec must rebuild"

        log = ResultsLog(root / "results" / "r.jsonl", {"k": 5})
        log.write({"arm": "dense", "item_id": "q1", "metrics": {"hit": 1}})
        again = ResultsLog(root / "results" / "r.jsonl", {"k": 5})
        assert again.done("dense", "q1") and not again.done("dense", "q2")
        other = ResultsLog(root / "results" / "r.jsonl", {"k": 10})
        assert not other.done("dense", "q1"), "rows from another config must not count"
        with open(root / "results" / "r.jsonl", "a", encoding="utf-8") as f:
            f.write('{"arm": "dense", "item_id": "q2", "metr')      # a crash mid-append
        torn = ResultsLog(root / "results" / "r.jsonl", {"k": 5})
        torn.write({"arm": "dense", "item_id": "q2", "metrics": {}})
        torn.write({"arm": "dense", "item_id": "q3", "error": "ConnectionError: refused"})
        again = ResultsLog(root / "results" / "r.jsonl", {"k": 5})   # must not raise
        assert again.done("dense", "q2") and not again.done("dense", "q3"), "transient errors retry"
        again.write({"arm": "dense", "item_id": "q3", "metrics": {"hit": 0}})
        assert len([r for r in again.rows() if r["item_id"] == "q3"]) == 1, "latest row wins"

        try:
            import numpy as np
        except ImportError:
            print("numpy not installed: cached_matrix not tested")
        else:
            enc_calls = []

            def encode(batch):
                enc_calls.append(len(batch))
                return np.ones((len(batch), 3))

            ids = [f"c{i}" for i in range(10)]
            m1 = cached_matrix("t", {"model": "fake"}, ids, ids, encode, art_dir=root, shard_rows=4)
            m2 = cached_matrix("t", {"model": "fake"}, ids, ids, encode, art_dir=root, shard_rows=4)
            assert m1.shape == (10, 3) and (m1 == m2).all() and sum(enc_calls) == 10
            changed = [t + " [prefix]" for t in ids]                  # same ids, new texts
            cached_matrix("t", {"model": "fake"}, ids, changed, encode, art_dir=root, shard_rows=4)
            assert sum(enc_calls) == 20, "changed texts under the same ids must re-encode"

        pack_for_review(root)
        print("store.py selftest: OK")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
