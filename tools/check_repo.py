"""
Repository hygiene checks. Run before committing; exits non-zero on any problem.

    python tools/check_repo.py
    python tools/check_repo.py --publish     # also fail on the placeholder REPO_URL

Checks:
  1. every stage notebook is fresh and every code cell is plain Python (py_to_notebook --check)
  2. tracked text files use LF line endings
  3. no absolute user paths (C:\\Users\\..., /home/...) in tracked files
  4. every tracked .json / .jsonl / .ipynb parses
  5. no notebook carries outputs
  6. each module's "Public API:" docstring block names exactly its public top-level definitions
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import py_to_notebook  # noqa: E402

TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".jsonl", ".ipynb", ".cfg", ".toml", ""}
USER_PATH = re.compile(r"(?i)\b[a-z]:(?:\\{1,2}|/)users(?:\\{1,2}|/)\w|(?<![\w.])/(?:home|Users)/\w")


def tracked_files() -> list[Path]:
    r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
                       capture_output=True, text=True, check=True)
    return [ROOT / p for p in r.stdout.splitlines() if (ROOT / p).is_file()]


def _names(body) -> set[str]:
    """Top-level names a module defines: defs, classes, assignments, imports -- also inside
    top-level if/try blocks (platform-conditional definitions)."""
    out: set[str] = set()
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            for target in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                out |= {x.id for x in ast.walk(target) if isinstance(x, ast.Name)}
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, (ast.If, ast.Try)):
            handlers = [s for h in getattr(n, "handlers", []) for s in h.body]
            out |= _names(n.body + n.orelse + handlers + getattr(n, "finalbody", []))
    return out


def public_api_problems(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc = ast.get_docstring(tree) or ""
    # The block ends at the first line holding anything besides identifiers and commas.
    m = re.search(r"Public API:[ \t]*\n((?:[ \t]+[\w, ]+(?:\n|$))+)", doc)
    if not m:
        return []
    listed = {x.strip() for x in re.split(r"[,\s]+", m.group(1)) if x.strip()}
    functions_and_classes = {n.name for n in tree.body if isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not n.name.startswith("_")}
    problems = []
    missing = sorted(functions_and_classes - listed)
    stale = sorted(listed - _names(tree.body))
    if missing:
        problems.append(f"{path.name}: public but not in 'Public API:' -> {', '.join(missing)}")
    if stale:
        problems.append(f"{path.name}: listed in 'Public API:' but not defined -> {', '.join(stale)}")
    return problems


def main() -> int:
    publish = "--publish" in sys.argv
    problems: list[str] = []

    # 1. notebooks
    for stem, (source, destination) in py_to_notebook.STAGES.items():
        if not source.is_file():
            continue
        text, _, cell_problems = py_to_notebook.render(source)
        problems += cell_problems
        if not destination.is_file():
            problems.append(f"{destination.name}: missing (run tools/py_to_notebook.py)")
        elif destination.read_bytes() != text.encode("utf-8"):
            problems.append(f"{destination.name}: stale (run tools/py_to_notebook.py)")
    if publish and py_to_notebook.URL_PLACEHOLDER in py_to_notebook.REPO_URL:
        problems.append("REPO_URL is still the placeholder (tools/py_to_notebook.py)")

    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix not in TEXT_SUFFIXES:
            continue
        data = path.read_bytes()
        # 2. line endings
        if b"\r\n" in data:
            problems.append(f"{rel}: CRLF line endings")
        text = data.decode("utf-8", errors="replace")
        # 3. absolute user paths
        if USER_PATH.search(text) and rel != "tools/check_repo.py":
            problems.append(f"{rel}: contains an absolute user path")
        # 4. parseable data files, 5. no outputs
        if path.suffix in (".json", ".ipynb"):
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as e:
                problems.append(f"{rel}: invalid JSON ({e})")
                continue
            if path.suffix == ".ipynb" and any(c.get("outputs") for c in obj.get("cells", [])):
                problems.append(f"{rel}: has outputs committed")
        elif path.suffix == ".jsonl":
            for i, line in enumerate(text.splitlines(), start=1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        problems.append(f"{rel}:{i}: invalid JSONL ({e})")
                        break
        # 6. public API docstrings
        if path.suffix == ".py" and path.parent == ROOT:
            problems += public_api_problems(path)

    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("check_repo: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
