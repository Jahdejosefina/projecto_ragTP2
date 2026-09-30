"""
What the stages print, and the record each stage leaves behind.

    from console import print_table, verdict, StageRun

Public API:
    print_table, verdict, wrap, clip, StageRun

A diagnostic here always ends in a VERDICT STRING, never in a bare number: "0.93x --
comparable" or "2.1x -- NOT comparable, read the note above". A number you have to
interpret is a number you'll misread at 2 a.m.; the verdict says what it means, and the
threshold it used, so you can disagree with it.
"""

from __future__ import annotations

import json
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

SMOKE_BANNER = "SMOKE_TEST -- these numbers mean nothing; they only prove the code runs"


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}" if abs(value) < 100 else f"{value:,.0f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def _is_number(value: Any) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))


def print_table(title: str, columns: Sequence[str],
                rows: Iterable[tuple[str, dict[str, Any]]], *, smoke: bool = False,
                name_header: str = "") -> None:
    """Print a fixed-width table.

    `rows` is a list of (row_name, {column: value}); missing columns print as "—".
    With `smoke=True` the table carries a banner so a smoke number can't be pasted into
    a report by accident.
    """
    rows = list(rows)
    cells = [[name] + [_fmt(vals.get(c)) for c in columns] for name, vals in rows]
    header = [name_header] + list(columns)
    widths = [max(len(str(x)) for x in col) for col in zip(header, *cells)] if cells else \
        [len(h) for h in header]
    line = "-" * (sum(widths) + 3 * (len(widths) - 1))
    print()
    print(title)
    if smoke:
        print(f"[{SMOKE_BANNER}]")
    print(line)
    numeric = [all(_is_number(vals.get(c)) for _, vals in rows) for c in columns]
    print(" | ".join(h.rjust(w) if i and numeric[i - 1] else h.ljust(w)
                     for i, (h, w) in enumerate(zip(header, widths))))
    print(line)
    for row in cells:
        print(" | ".join(v.rjust(w) if i and numeric[i - 1] else v.ljust(w)
                         for i, (v, w) in enumerate(zip(row, widths))))
    print(line)


def verdict(ok: bool, good: str, bad: str) -> str:
    """'OK -- <good>' or 'CHECK -- <bad>'. Put the threshold you used inside the strings."""
    return f"OK -- {good}" if ok else f"CHECK -- {bad}"


def wrap(text: str, width: int = 74, indent: str = "   ", max_lines: int | None = None) -> str:
    """Wrap prose for printing; `max_lines` truncates with an ellipsis."""
    lines = textwrap.wrap(" ".join(str(text).split()), width=width,
                          initial_indent=indent, subsequent_indent=indent)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + " …"
    return "\n".join(lines)


def clip(text: str, n: int = 160) -> str:
    """One line, at most `n` characters."""
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _peak_vram_gb() -> float | None:
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    return round(torch.cuda.max_memory_reserved() / 1e9, 2)


def _llm_stats() -> dict:
    llm = sys.modules.get("llm")
    return dict(getattr(llm, "STATS", {})) if llm is not None else {}


class StageRun:
    """The record a stage leaves in `run_report.json`: what ran, how long, at what cost.

        run = StageRun.start("03_retrieval", ART, profile=PROFILE, config={...})  # config cell
        ...
        run.note("n_chunks", len(chunks))
        run.finish()                                                              # last cell

    It spans notebook cells, so it can't be a `with` block. A stage that crashes stays
    `started` in the report, which is exactly what you want to see the next morning.
    """

    def __init__(self, stage: str, art_dir: Path, profile: str, config: dict):
        self.stage = stage
        self.path = Path(art_dir) / "run_report.json"
        self.record: dict[str, Any] = {
            "stage": stage, "profile": profile, "config": config, "status": "started",
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "notes": {},
        }
        self._t0 = time.time()
        self._llm0 = _llm_stats()
        self._save()

    @classmethod
    def start(cls, stage: str, art_dir: str | Path, *, profile: str, config: dict | None = None) -> "StageRun":
        run = cls(stage, Path(art_dir), profile, config or {})
        print(f"== {stage} · profile {profile} · report -> {run.path}")
        return run

    def note(self, key: str, value: Any) -> None:
        self.record["notes"][key] = value
        self._save()

    def finish(self, status: str = "ok") -> dict:
        now = _llm_stats()
        self.record["llm"] = {k: now.get(k, 0) - self._llm0.get(k, 0)
                              for k in now if isinstance(now.get(k), (int, float))}
        self.record.update(status=status, wall_s=round(time.time() - self._t0, 1),
                           peak_vram_gb=_peak_vram_gb(),
                           finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        self._save()
        print(f"== {self.stage} finished: {status} in {self.record['wall_s']} s"
              + (f" · LLM calls {self.record['llm'].get('calls', 0)}" if self.record["llm"] else ""))
        return self.record

    def _save(self) -> None:
        from store import write_json  # atomic: a disconnect mid-write can't tear the report

        report = {}
        if self.path.is_file():
            try:
                report = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                corrupt = self.path.with_suffix(".corrupt.json")
                self.path.replace(corrupt)
                print(f"WARNING: {self.path.name} was unreadable; kept as {corrupt.name}", file=sys.stderr)
        report[self.stage] = self.record
        write_json(self.path, report)
