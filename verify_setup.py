"""
Checks that your environment is ready for the lab.

    python verify_setup.py                     # environment, packages, Hub, Ollama server
    python verify_setup.py --model qwen3:8b    # also probe a pulled model (thinking, token counts)

Run it before you start, while you have internet. It never downloads model weights: the
Hub checks are metadata calls, check 5 fetches only a small Qwen3 tokenizer (a few MB) into
HF_HOME, and `--model` only talks to a model you already pulled (plus its tokenizer).

The package check runs BEFORE `environment` is imported, so a fresh venv with nothing
installed gets a list of what's missing instead of an ImportError from the wiring.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OK, FAIL, WARN = "  OK  ", " FAIL ", " WARN "
problems: list[str] = []

# requirement name -> import name, where they differ
IMPORT_NAMES = {"sentence-transformers": "sentence_transformers", "PyStemmer": "Stemmer",
                "beautifulsoup4": "bs4", "huggingface_hub": "huggingface_hub"}

# models assignment.md §7 suggests (metadata check only)
HUB_MODELS = ("BAAI/bge-m3", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
              "intfloat/multilingual-e5-small", "Qwen/Qwen3-8B")


def check(title: str, fn, *, warn_only: bool = False) -> bool:
    try:
        detail = fn()
    except Exception as e:
        tag = WARN if warn_only else FAIL
        if not warn_only:
            problems.append(title)
        print(f"[{tag}] {title}")
        print(f"          {type(e).__name__}: {e}")
        return False
    print(f"[{OK}] {title}")
    for line in (detail or "").splitlines():
        print(f"          {line}")
    return True


def check_python():
    v = sys.version_info
    if v < (3, 10):
        raise RuntimeError(f"Python {v.major}.{v.minor} is too old; need 3.10+ (Colab runs 3.12+)")
    venv = "" if sys.prefix != sys.base_prefix else "\nWARNING: no virtual environment seems active."
    return f"Python {v.major}.{v.minor}.{v.micro} at {sys.executable}{venv}"


def _requirements() -> list[tuple[str, str, str]]:
    """(name, operator, version) for every line of requirements.txt."""
    out = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=)?\s*([^,;\s]*)", line)
        if m:
            out.append((m.group(1), m.group(2) or "", m.group(3) or ""))
    return out


def check_packages():
    missing, wrong, lines = [], [], []
    for name, op, pinned in _requirements():
        module = IMPORT_NAMES.get(name, name.replace("-", "_"))
        if importlib.util.find_spec(module) is None:
            missing.append(name)
            continue
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = "?"
        mark = ""
        if op == "==" and installed != pinned:
            wrong.append(f"{name} {installed} (pinned {pinned})")
            mark = "   <-- differs from the pin"
        lines.append(f"{name} {installed}{mark}")
    if missing:
        raise ImportError(f"missing: {', '.join(missing)}. Run: pip install -r requirements.txt")
    if wrong:
        lines.append("Pinned versions differ -- behaviour may differ from what llm.py and the assignment describe:")
        lines += [f"  {w}" for w in wrong]
    return "\n".join(lines)


def check_environment():
    import environment

    info = environment.diagnostics()
    if not info.get("jax_guard"):
        raise RuntimeError("the JAX guard is not set: import `environment` before anything else")
    return "\n".join(f"{k}: {v}" for k, v in info.items())


def check_hub():
    from huggingface_hub import HfApi

    api, lines = HfApi(), []
    for repo in HUB_MODELS:
        info = api.model_info(repo)
        lines.append(f"{repo} @ {info.sha[:12]}")
    return "\n".join(lines) + "\n(metadata only -- nothing was downloaded)"


def check_tokenizer():
    """The chat-template token count llm.py relies on, on a tiny Qwen3 tokenizer."""
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B")
    msgs = [{"role": "user", "content": "¿Qué es una ventana de contexto?"}]
    enc = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                                  enable_thinking=False, return_dict=True)
    ids = enc["input_ids"]
    if not isinstance(ids, list) or not ids or not isinstance(ids[0], int):
        raise TypeError(f"apply_chat_template returned {type(ids)}, expected a list of ints")
    bare = len(tok.encode(msgs[0]["content"], add_special_tokens=False))
    return (f"template count {len(ids)} tokens vs {bare} for the bare text -- the template adds "
            f"{len(ids) - bare} (that's why prompts are counted with it)")


def check_git_disk():
    if shutil.which("git") is None:
        raise RuntimeError("git is not on PATH (corpora are fetched with git)")
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    note = "" if free_gb > 25 else "\nWARNING: under 25 GB free; the full profile's models and caches need ~20 GB."
    return f"git: {shutil.which('git')}\nfree disk: {free_gb:.0f} GB{note}"


def check_ollama():
    import llm

    path = llm.ollama_bin()
    if llm.server_alive():
        running = llm.server_version()
        lines = [f"server: {llm.HOST}, version {running}"]
        if running != llm.OLLAMA_VERSION:
            lines.append(f"note: llm.py's facts were checked on {llm.OLLAMA_VERSION}")
        if path is None:
            lines.append("note: the server runs, but the `ollama` command is not on PATH (fine for the lab)")
        elif not shutil.which("ollama"):
            lines.append(f"note: `ollama` is not on PATH; the binary is at {path}. Add its folder to "
                         "your PATH to use it from a terminal.")
        return "\n".join(lines)
    if path is None:
        raise RuntimeError("Ollama is not installed. Locally: https://ollama.com/download. "
                           "On Colab the notebooks install it for you (llm.setup).")
    raise RuntimeError(f"Ollama is installed ({path}) but no server answers on {llm.HOST}. "
                       "Start it (the desktop app, or `ollama serve`) and re-run.")


def check_model(model: str):
    import llm

    if llm.model_digest(model) is None:
        raise RuntimeError(f"{model} is not pulled. Run: ollama pull {model}")
    info = llm.setup(model, num_ctx=4096, pull_model=False)
    return f"{model} ready: {info.get('placement')}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="also probe this already-pulled Ollama model")
    args = ap.parse_args()

    print("Checking the environment for the Retrieval & Memory Lab\n")
    check("1. Python", check_python)
    if not check("2. Packages (requirements.txt)", check_packages):
        print("\nInstall the requirements first; the remaining checks need them.")
        return 1
    check("3. Environment wiring", check_environment)
    check("4. HuggingFace Hub reachable", check_hub)
    check("5. Chat-template token counting", check_tokenizer)
    check("6. git and disk", check_git_disk)
    check("7. Ollama server", check_ollama, warn_only=not args.model)
    if args.model:
        check(f"8. Model {args.model}", lambda: check_model(args.model))

    print()
    if problems:
        print(f"{len(problems)} check(s) failed:")
        for p in problems:
            print(f"  - {p}")
        print("\nSee the Setup section of README.md.")
        return 1
    print("Everything's in order. Start with 00_corpus_audit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
