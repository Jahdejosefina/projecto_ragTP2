"""
The artifact contract: what a document, an eval item, a conversation script, a memory
scenario and a result row look like on disk -- and the checks that hold them to it.

    from schema import Document, EvalItem, validate_documents, freeze_eval, load_eval

Public API:
    SCHEMA_VERSION, CATEGORIES, DEPENDENCIES, ABILITIES,
    Section, DocMetadata, Document, Gold, EvalItem,
    DialogueTurn, Dialogue, ScriptTurn, Session, Probe, Scenario, ResultRow,
    ValidationReport, EvalChanged, EvalSet,
    documents_hash, validate_documents, validate_eval, freeze_eval, load_eval

WHY A SHARED CONTRACT
---------------------
Stages hand work to each other -- and group members hand work to each other -- through
these files. If Stage 1 writes `id` and Stage 3 reads `doc_id`, nothing fails: the join
comes back empty and every metric is zero, or worse, the join half-works. A schema that
every stage validates against turns that into an error on line one.

What the contract deliberately does NOT decide: what a document IS in your corpus, how
you cut sections, which metadata you keep, what your categories mean. Those are the
graded decisions of Stages 1-2. The contract only makes sure the next stage can read them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from store import canonical_json, read_json, read_jsonl, sha256_json, sha256_text, write_json

SCHEMA_VERSION = 1

# Suggested vocabularies. Your own labels are allowed; these are what the tables group by
# if you use them. Spelling matters: "out-of-corpus" is not "out_of_corpus".
CATEGORIES = ("topical", "identifier", "metadata", "out_of_corpus")
DEPENDENCIES = ("standalone", "coreference", "ellipsis", "topic_shift", "return", "unanswerable")
ABILITIES = ("extraction", "multi_session", "temporal", "knowledge_update", "abstention", "preference")

# For yes/no questions ("can I use X in 3.12?"). An answer key can't say no: "No, X arrived in 3.13" and
# "Yes, X is there since 3.13" both contain "3.13". The verdict is scored separately (Stage 2).
_VERDICT = "for a yes/no question: the right verdict, scored apart from the answer key"


# --- documents --------------------------------------------------------------------------------
class Section(BaseModel):
    """A structural unit of a document, as character offsets into `Document.text`."""
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(min_length=1, description="stable: doc_id + structural path, never row order")
    title: str = ""
    level: int = Field(default=1, ge=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    parent_id: str | None = None

    @model_validator(mode="after")
    def _span(self):
        if self.end < self.start:
            raise ValueError(f"section {self.section_id}: end {self.end} < start {self.start}")
        return self


class DocMetadata(BaseModel):
    """Common fields plus anything your corpus has (extra keys are kept)."""
    model_config = ConfigDict(extra="allow")

    version: str | None = None
    date: str | None = Field(default=None, description="ISO date of the content, if known")
    status: Literal["current", "superseded", "deprecated", "draft", "unknown"] = "unknown"
    source_url: str | None = None
    lang: str | None = None


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=1, pattern=r"^\S+$")
    title: str = ""
    text: str = Field(min_length=1)
    sections: list[Section] = []
    metadata: DocMetadata = DocMetadata()


# --- single-turn eval -------------------------------------------------------------------------------
class Gold(BaseModel):
    """Where the answer lives. `section_id` is what lets you tell 'the document arrived'
    from 'the passage that answers arrived' -- label it whenever you can."""
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    section_id: str | None = None


class EvalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    category: str = Field(description="e.g. one of CATEGORIES")
    gold: list[Gold] = Field(default_factory=list, description="a SET when versions/copies are interchangeable")
    answerable: bool = True
    answer_key: list[str] | None = Field(default=None, description="short strings a correct answer contains")
    expected_verdict: Literal["yes", "no"] | None = Field(default=None, description=_VERDICT)
    split: Literal["dev", "test"] = "test"
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self):
        if self.answerable and not self.gold:
            raise ValueError(f"{self.item_id}: answerable but no gold")
        if not self.answerable and self.gold:
            raise ValueError(f"{self.item_id}: unanswerable items have no gold")
        if not self.answerable and self.expected_verdict:
            raise ValueError(f"{self.item_id}: unanswerable items have no verdict")
        return self


# --- conversations (Stage 5) ------------------------------------------------------------------------
class DialogueTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=1)
    user: str = Field(min_length=1)
    assistant: str | None = Field(default=None, description="scripted reply used as history (teacher forcing)")
    depends_on: str = Field(default="standalone", description="e.g. one of DEPENDENCIES")
    oracle_rewrite: str | None = Field(default=None, description="hand-written standalone version of `user`")
    gold: list[Gold] = Field(default_factory=list)
    answerable: bool = True
    answer_key: list[str] | None = None
    expected_verdict: Literal["yes", "no"] | None = Field(default=None, description=_VERDICT)

    @model_validator(mode="after")
    def _consistent(self):
        if self.depends_on == "unanswerable" and self.answerable:
            raise ValueError(f"turn {self.turn}: depends_on='unanswerable' needs answerable=False")
        if not self.answerable and self.gold:
            raise ValueError(f"turn {self.turn}: unanswerable turns have no gold")
        if not self.answerable and self.expected_verdict:
            raise ValueError(f"turn {self.turn}: unanswerable turns have no verdict")
        return self


class Dialogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialogue_id: str = Field(min_length=1)
    turns: list[DialogueTurn] = Field(min_length=1)
    split: Literal["dev", "test"] = "test"
    notes: str = ""

    @model_validator(mode="after")
    def _ordered(self):
        numbers = [t.turn for t in self.turns]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError(f"{self.dialogue_id}: turns must be numbered 1..n in order, got {numbers}")
        return self


# --- multi-session memory scenarios (Stage 6) ---------------------------------------------------------
class ScriptTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(min_length=1)
    assistant: str | None = None


class Session(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    date: str = Field(description="SIMULATED ISO datetime -- recency is computed from this, not the wall clock")
    turns: list[ScriptTurn] = Field(min_length=1)


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_id: str = Field(min_length=1)
    after_session: str = Field(description="the probe is asked in a new session after this one")
    question: str = Field(min_length=1)
    ability: str = Field(description="e.g. one of ABILITIES")
    evidence_sessions: list[str] = Field(default_factory=list, description="where the needed fact was stated")
    answerable: bool = True
    answer_key: list[str] | None = None
    expected_verdict: Literal["yes", "no"] | None = Field(default=None, description=_VERDICT)
    gold: list[Gold] = Field(default_factory=list, description="corpus passages, if the probe also needs retrieval")
    notes: str = ""

    @model_validator(mode="after")
    def _verdict(self):
        if not self.answerable and self.expected_verdict:
            raise ValueError(f"{self.probe_id}: unanswerable probes have no verdict")
        return self


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    persona: str = Field(description="fictional -- no real personal data")
    sessions: list[Session] = Field(min_length=1)
    probes: list[Probe] = Field(min_length=1)
    split: Literal["dev", "test"] = "test"

    @model_validator(mode="after")
    def _refs(self):
        ids = [s.session_id for s in self.sessions]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.scenario_id}: duplicate session_id in {ids}")
        pids = [p.probe_id for p in self.probes]
        if len(set(pids)) != len(pids):
            raise ValueError(f"{self.scenario_id}: duplicate probe_id in {pids}")
        try:
            dates = [datetime.fromisoformat(s.date) for s in self.sessions]
        except ValueError as e:
            raise ValueError(f"{self.scenario_id}: a session date is not ISO 8601 ({e})") from e
        if dates != sorted(dates):
            raise ValueError(f"{self.scenario_id}: sessions are not in chronological order")
        for p in self.probes:
            if p.after_session not in ids:
                raise ValueError(f"{self.scenario_id}/{p.probe_id}: unknown after_session {p.after_session!r}")
            for e in p.evidence_sessions:
                if e not in ids:
                    raise ValueError(f"{self.scenario_id}/{p.probe_id}: unknown evidence session {e!r}")
                if ids.index(e) > ids.index(p.after_session):
                    raise ValueError(f"{self.scenario_id}/{p.probe_id}: evidence {e!r} comes after the probe")
            if p.answerable != bool(p.evidence_sessions or p.gold):
                raise ValueError(f"{self.scenario_id}/{p.probe_id}: answerable must match having evidence")
        return self


# --- results ---------------------------------------------------------------------------------------------
class ResultRow(BaseModel):
    """One item under one arm. Failures are rows too: `error` set, `metrics` possibly empty.
    `store.ResultsLog` writes these (it adds `config_key`); `stage` is yours to set."""
    model_config = ConfigDict(extra="allow")

    stage: str | None = None
    arm: str
    item_id: str
    config_key: str
    metrics: dict = {}
    llm: dict | None = None
    output: dict | None = None
    error: str | None = None


# --- validation -------------------------------------------------------------------------------------------
@dataclass
class ValidationReport:
    what: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def show(self, max_lines: int = 20) -> "ValidationReport":
        print(f"{self.what}: " + ("OK" if self.ok else f"{len(self.errors)} ERROR(S)")
              + (f", {len(self.warnings)} warning(s)" if self.warnings else ""))
        for k, v in self.counts.items():
            print(f"   {k}: {v}")
        for e in self.errors[:max_lines]:
            print(f"   ERROR   {e}")
        for w in self.warnings[:max_lines]:
            print(f"   warning {w}")
        hidden = max(0, len(self.errors) - max_lines) + max(0, len(self.warnings) - max_lines)
        if hidden:
            print(f"   ... and {hidden} more")
        return self

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise ValueError(f"{self.what}: {len(self.errors)} error(s), first: {self.errors[0]}")


def documents_hash(docs: list[Document]) -> str:
    """Hash of the corpus CONTENT, independent of the order the documents were written in."""
    ordered = sorted((d.model_dump(mode="json") for d in docs), key=lambda d: d["doc_id"])
    return sha256_text(canonical_json(ordered))


def _first_error(e: ValidationError) -> str:
    """'field.path: message (+N more)' -- the useful part of a pydantic error."""
    first = e.errors()[0]
    where = ".".join(str(x) for x in first["loc"]) or "(model)"
    more = f" (+{e.error_count() - 1} more)" if e.error_count() > 1 else ""
    return f"{where}: {first['msg']}{more}"


def validate_documents(path: str | Path) -> ValidationReport:
    """Every line a valid Document; unique doc_ids; sections inside the text, sorted, unique."""
    report = ValidationReport(f"documents ({Path(path).name})")
    docs: list[Document] = []
    for i, row in enumerate(read_jsonl(path), start=1):
        try:
            docs.append(Document.model_validate(row))
        except ValidationError as e:
            report.errors.append(f"row {i} ({row.get('doc_id', '?')}): {_first_error(e)}")
    seen: set[str] = set()
    for d in docs:
        if d.doc_id in seen:
            report.errors.append(f"duplicate doc_id {d.doc_id}")
        seen.add(d.doc_id)
        sids = [s.section_id for s in d.sections]
        if len(sids) != len(set(sids)):
            report.errors.append(f"{d.doc_id}: duplicate section ids")
        for s in d.sections:
            if s.end > len(d.text):
                report.errors.append(f"{d.doc_id}/{s.section_id}: end {s.end} past text length {len(d.text)}")
        starts = [s.start for s in d.sections]
        if starts != sorted(starts):
            report.warnings.append(f"{d.doc_id}: sections not sorted by start")
        if not d.sections:
            report.warnings.append(f"{d.doc_id}: no sections (section-level gold impossible)")
    report.counts = {
        "documents": len(docs),
        "sections": sum(len(d.sections) for d in docs),
        "characters": sum(len(d.text) for d in docs),
        "with version": sum(1 for d in docs if d.metadata.version),
        "with date": sum(1 for d in docs if d.metadata.date),
    }
    if len(report.warnings) > 20:
        n_nosec = sum(1 for w in report.warnings if "no sections" in w)
        if n_nosec:
            report.warnings = [w for w in report.warnings if "no sections" not in w] + \
                              [f"{n_nosec} documents have no sections"]
    return report


EVAL_FILES = {"single_turn.jsonl": EvalItem, "dialogues.jsonl": Dialogue, "scenarios.jsonl": Scenario}


def _gold_errors(where: str, golds: list[Gold], sections_of: dict[str, set[str]]) -> list[str]:
    errors = []
    for g in golds:
        if g.doc_id not in sections_of:
            errors.append(f"{where}: gold doc {g.doc_id!r} is not in the documents")
        elif g.section_id is not None and g.section_id not in sections_of[g.doc_id]:
            errors.append(f"{where}: gold section {g.section_id!r} is not a section of {g.doc_id}")
    return errors


def validate_eval(eval_dir: str | Path, documents_path: str | Path) -> ValidationReport:
    """Parse the eval files and check every gold id against the documents, at both levels."""
    eval_dir = Path(eval_dir)
    report = ValidationReport(f"eval set ({eval_dir})")
    docs = [Document.model_validate(r) for r in read_jsonl(documents_path)]
    sections_of = {d.doc_id: {s.section_id for s in d.sections} for d in docs}

    if not (eval_dir / "single_turn.jsonl").is_file():
        report.errors.append("single_turn.jsonl is missing")
    loaded: dict[str, list] = {}
    id_field = {"single_turn.jsonl": "item_id", "dialogues.jsonl": "dialogue_id",
                "scenarios.jsonl": "scenario_id"}
    for name, model in EVAL_FILES.items():
        path = eval_dir / name
        if not path.is_file():
            continue
        loaded[name] = []
        for i, raw in enumerate(read_jsonl(path), start=1):  # row by row: report every bad row
            try:
                loaded[name].append(model.model_validate(raw))
            except ValidationError as e:
                report.errors.append(f"{name} row {i} ({raw.get(id_field[name], '?')}): {_first_error(e)}")

    items = loaded.get("single_turn.jsonl", [])
    ids = [x.item_id for x in items]
    if len(ids) != len(set(ids)):
        report.errors.append("single_turn: duplicate item_id")
    for x in items:
        report.errors += _gold_errors(x.item_id, x.gold, sections_of)
        if x.answerable and not any(g.section_id for g in x.gold):
            report.warnings.append(f"{x.item_id}: no section-level gold")
    for d in loaded.get("dialogues.jsonl", []):
        for t in d.turns:
            report.errors += _gold_errors(f"{d.dialogue_id}#{t.turn}", t.gold, sections_of)
            if t.answerable and not t.gold:
                report.warnings.append(f"{d.dialogue_id}#{t.turn}: answerable but no gold (chit-chat?)")
            if t.turn > 1 and not t.oracle_rewrite:
                report.warnings.append(f"{d.dialogue_id}#{t.turn}: no oracle_rewrite")
    for s in loaded.get("scenarios.jsonl", []):
        for p in s.probes:
            report.errors += _gold_errors(f"{s.scenario_id}/{p.probe_id}", p.gold, sections_of)

    by_cat: dict[str, int] = {}
    for x in items:
        by_cat[x.category] = by_cat.get(x.category, 0) + 1
    if items and not any(not x.answerable for x in items):
        report.errors.append("single_turn: no unanswerable (out-of-corpus) item -- abstention can't be measured")
    abilities: dict[str, int] = {}
    for s in loaded.get("scenarios.jsonl", []):
        for p in s.probes:
            abilities[p.ability] = abilities.get(p.ability, 0) + 1
    splits = {s: sum(1 for x in items if x.split == s) for s in ("dev", "test")}
    report.counts = {
        "single-turn items": len(items),
        "by split": splits,
        "by category": by_cat,
        "dialogues": len(loaded.get("dialogues.jsonl", [])),
        "dialogue turns": sum(len(d.turns) for d in loaded.get("dialogues.jsonl", [])),
        "scenarios": len(loaded.get("scenarios.jsonl", [])),
        "probes by ability": abilities,
        "yes/no rows (expected_verdict)": sum(x.expected_verdict is not None for x in items)
        + sum(t.expected_verdict is not None for d in loaded.get("dialogues.jsonl", []) for t in d.turns)
        + sum(p.expected_verdict is not None for s in loaded.get("scenarios.jsonl", []) for p in s.probes),
    }
    return report


class EvalChanged(RuntimeError):
    """The eval set on disk is not the one that was frozen."""


def _file_digest(path: Path, model: type) -> tuple[int, str]:
    rows = [r.model_dump(mode="json") for r in read_jsonl(path, model)]
    return len(rows), sha256_text(canonical_json(rows))


def freeze_eval(eval_dir: str | Path, documents_path: str | Path) -> dict:
    """Write `FROZEN.json`: one hash per eval file (over parsed rows) plus the corpus hash.

    Freeze BEFORE you compute the first result you intend to report, and commit it. Every
    later edit is a decision-log entry, and every number computed before the edit is either
    re-run or dropped.
    """
    report = validate_eval(eval_dir, documents_path).show()
    report.raise_if_failed()
    eval_dir = Path(eval_dir)
    docs = [Document.model_validate(r) for r in read_jsonl(documents_path)]
    files = {}
    for name, model in EVAL_FILES.items():
        path = eval_dir / name
        if path.is_file():
            n, digest = _file_digest(path, model)
            files[name] = {"rows": n, "sha256_canonical": digest}
    frozen = {"schema_version": SCHEMA_VERSION, "files": files,
              "documents_sha256": documents_hash(docs), "counts": report.counts}
    write_json(eval_dir / "FROZEN.json", frozen)
    listing = ", ".join("%s (%d rows)" % (k, v["rows"]) for k, v in files.items())
    print(f"frozen: {listing}")
    return frozen


@dataclass
class EvalSet:
    items: list[EvalItem]
    dialogues: list[Dialogue]
    scenarios: list[Scenario]
    frozen: dict | None

    def split(self, name: str) -> "EvalSet":
        """Only the rows with `split == name`. Raises if there are none (the default is 'test')."""
        out = EvalSet([x for x in self.items if x.split == name],
                      [d for d in self.dialogues if d.split == name],
                      [s for s in self.scenarios if s.split == name], self.frozen)
        if not (out.items or out.dialogues or out.scenarios):
            raise ValueError(f"no eval rows with split={name!r} (every row defaults to 'test'): "
                             "set `split` in the eval files")
        return out

    def key(self) -> str:
        """What results rows should be keyed on (`ResultsLog`'s run_spec): the frozen hashes -- or,
        for an unfrozen set such as eval/smoke, a hash of the rows themselves, so an edited smoke
        item is recomputed instead of resumed."""
        if self.frozen:
            return sha256_json(self.frozen)
        return sha256_json([r.model_dump(mode="json") for r in (*self.items, *self.dialogues, *self.scenarios)])


def load_eval(eval_dir: str | Path, *, require_frozen: bool = True,
              documents_path: str | Path | None = None) -> EvalSet:
    """Load the eval set; with `require_frozen`, raise EvalChanged if it differs from FROZEN.json.

    With `documents_path` too, also raise if the CORPUS changed since the freeze: gold ids
    frozen against one documents.jsonl can point at missing or different text in another
    (a new cleaning rule, a re-cut section, the smoke subset instead of the full corpus).
    With `require_frozen=False` nothing is checked -- an unfrozen set has no hashes to compare
    with, and `documents_path` is ignored: check its gold ids with `validate_eval`.

    Call this at the top of every notebook that computes a metric.
    """
    eval_dir = Path(eval_dir)
    frozen_path = eval_dir / "FROZEN.json"
    frozen = read_json(frozen_path) if frozen_path.is_file() else None
    if require_frozen:
        if frozen is None:
            raise EvalChanged(f"{frozen_path} not found: freeze the eval set (Stage 2) before measuring.")
        for name, model in EVAL_FILES.items():
            path = eval_dir / name
            pinned = frozen["files"].get(name)
            if pinned is None and not path.is_file():
                continue
            if pinned is None or not path.is_file():
                raise EvalChanged(f"{name}: present in one of (disk, FROZEN.json) but not the other.")
            n, digest = _file_digest(path, model)
            if digest != pinned["sha256_canonical"]:
                raise EvalChanged(
                    f"{name} changed since it was frozen ({pinned['rows']} -> {n} rows). "
                    "Either restore it, or re-freeze AND log the edit -- and re-run every result "
                    "computed against the old version.")
        if documents_path is not None:
            docs = [Document.model_validate(r) for r in read_jsonl(documents_path)]
            if documents_hash(docs) != frozen.get("documents_sha256"):
                raise EvalChanged(
                    f"{Path(documents_path).name} is not the corpus the eval set was frozen against: "
                    "gold ids may no longer point at the same text. Run validate_eval, re-freeze, "
                    "and log the change.")

    def load(name: str, model: type) -> list:
        path = eval_dir / name
        return read_jsonl(path, model) if path.is_file() else []

    return EvalSet(load("single_turn.jsonl", EvalItem), load("dialogues.jsonl", Dialogue),
                   load("scenarios.jsonl", Scenario), frozen)
