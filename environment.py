"""
Local environment wiring. Import this FIRST, before torch / transformers /
sentence_transformers / bm25s.

    import environment            # noqa: F401  (side effects)
    environment.summary()

WHAT THIS DOES, AND WHY
------------------------
1. Stops JAX from grabbing the GPU. `bm25s` imports `jax` when it is installed
   (it is, on Colab), and JAX PRE-ALLOCATES ~75% OF THE VRAM the moment its
   backend initializes: ~11 GB of a T4, gone in an import. PyTorch can't see
   it (it isn't PyTorch's), and neither can Ollama -- which then finds the card
   full and quietly splits the generator between GPU and CPU. There is no
   error. There is a generation that runs ~10x slower. The two variables below
   must be set before anything imports jax, which is why they come first.

2. Points the HuggingFace cache INSIDE the repo (`.hf_cache/`) unless HF_HOME
   was already set (the Colab bootstrap sets it to Drive when both USE_DRIVE and
   MODELS_ON_DRIVE are on).
   The embedder, the reranker and the generator's tokenizer all download
   through it. HF reads HF_HOME once, at import time: set it afterwards and it
   silently does nothing, so a late import is reported as a warning below.

3. Wires in a local certificate bundle if one is present (`.certs/ca_bundle.pem`,
   built by `tools/ca_bundle_windows.py`). On a network that inspects TLS
   (corporate, some campuses) HuggingFace downloads fail with
   CERTIFICATE_VERIFY_FAILED while the browser works fine. Its absence is the
   normal case.

4. Forces matplotlib's non-interactive `Agg` backend, but ONLY outside a
   Jupyter/Colab kernel: running a stage `.py` as a plain script on Windows
   otherwise inherits TkAgg, and `plt.show()` blocks forever waiting for a
   window nothing will close. Done through MPLBACKEND, so matplotlib is not
   imported here.

5. Reconfigures stdout/stderr to UTF-8. The Windows console is cp1252 by
   default, and Spanish text ("información", "¿") plus the replacement
   character from a broken decode crash a plain `print()` there otherwise.

6. Resolves the artifact directories -- `artifacts/smoke/` and
   `artifacts/full/`, kept apart on purpose so a smoke index can never be read
   as the real one -- WITHOUT creating them at import time. Creating
   `artifacts/` here would shadow the Drive symlink the Colab bootstrap makes
   when USE_DRIVE is on (a real directory silently wins over a link that
   arrives later). They are created on first use, by `artifacts_dir()`.

Everything is idempotent: a variable already set from outside is left alone.
"""

from __future__ import annotations

import os
import platform
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HF_CACHE = ROOT / ".hf_cache"
CA_BUNDLE = ROOT / ".certs" / "ca_bundle.pem"
ARTIFACTS = ROOT / "artifacts"
CORPORA = ROOT / "corpora"

# Packages whose versions end up in every manifest (see store.write_manifest).
TRACKED_PACKAGES = (
    "torch", "numpy", "transformers", "huggingface_hub", "sentence-transformers",
    "bm25s", "PyStemmer", "pydantic", "requests", "polib", "beautifulsoup4", "lxml",
)


def _set_if_missing(key: str, value: str) -> bool:
    """Set an environment variable only if it isn't already defined. True if it was set."""
    if os.environ.get(key):
        return False
    os.environ[key] = value
    return True


# --- 1. JAX must not pre-allocate the GPU (FIRST, before anything imports jax) ---------
_set_if_missing("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
_set_if_missing("JAX_PLATFORMS", "cpu")


def _warn_if_imported_too_late() -> None:
    """Point 1 and point 2 only work if they run before these packages are imported."""
    late = sorted(m for m in ("jax", "bm25s", "huggingface_hub", "transformers",
                              "sentence_transformers", "datasets") if m in sys.modules)
    if late:
        print(
            f"WARNING: {', '.join(late)} imported before `environment`. The JAX guard and the "
            "repo-local HuggingFace cache may NOT be in effect for them: restart the runtime "
            "and import `environment` first.",
            file=sys.stderr,
        )


_warn_if_imported_too_late()

# --- 2. HuggingFace cache inside the repo (unless the bootstrap put it on Drive) -------
if _set_if_missing("HF_HOME", str(HF_CACHE)):
    HF_CACHE.mkdir(parents=True, exist_ok=True)
_set_if_missing("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
_set_if_missing("TOKENIZERS_PARALLELISM", "false")  # fork-warning noise inside notebooks

# --- 3. corporate-proxy certificates ----------------------------------------------------
CA_BUNDLE_ACTIVE = False
if CA_BUNDLE.is_file():
    for _var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        _set_if_missing(_var, str(CA_BUNDLE))
    # The Rust downloader behind huggingface_hub (hf_xet) may not read SSL_CERT_FILE;
    # with the bundle active, fall back to plain HTTP downloads, which do.
    _set_if_missing("HF_HUB_DISABLE_XET", "1")
    CA_BUNDLE_ACTIVE = True


# --- 4. non-interactive matplotlib, outside a notebook kernel only ----------------------
def _in_notebook() -> bool:
    try:
        get_ipython  # type: ignore[name-defined]  # defined only inside IPython/Jupyter/Colab
    except NameError:
        return False
    return True


if not _in_notebook():
    _set_if_missing("MPLBACKEND", "Agg")

# --- 5. UTF-8 console -------------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


# --- public API ---------------------------------------------------------------------------
def on_colab() -> bool:
    """True inside a Google Colab runtime."""
    return "google.colab" in sys.modules or bool(os.environ.get("COLAB_RELEASE_TAG"))


def artifacts_dir(smoke: bool) -> Path:
    """`artifacts/smoke` or `artifacts/full`, created on first use.

    Warns if the Colab bootstrap asked for Drive persistence but `artifacts/` is a
    real directory: everything written there disappears with the runtime.
    """
    if os.environ.get("LAB_USE_DRIVE") == "1" and ARTIFACTS.is_dir() and not ARTIFACTS.is_symlink():
        print(
            "WARNING: USE_DRIVE is on but artifacts/ is a real directory, NOT the Drive link. "
            "Anything written now is lost when the runtime disconnects. Move its contents to "
            "Drive, delete it, and re-run the bootstrap cell.",
            file=sys.stderr,
        )
    path = ARTIFACTS / ("smoke" if smoke else "full")
    path.mkdir(parents=True, exist_ok=True)
    return path


def corpora_dir() -> Path:
    """Where raw corpus downloads live (gitignored, never vendored)."""
    CORPORA.mkdir(parents=True, exist_ok=True)
    return CORPORA


def has_cuda() -> bool:
    """True if a usable NVIDIA GPU is visible to torch. Lazy: doesn't import torch for free."""
    try:
        import torch
    except ImportError:
        return False
    return torch.cuda.is_available()


def device() -> str:
    """'cuda' or 'cpu'."""
    return "cuda" if has_cuda() else "cpu"


def seed_everything(seed: int) -> None:
    """Seed Python, numpy and torch (whichever are installed)."""
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass


def versions() -> dict:
    """Installed versions of the packages that decide what a result means."""
    from importlib.metadata import PackageNotFoundError, version

    out = {"python": sys.version.split()[0], "platform": platform.platform()}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = None
    return out


def _nvidia(query: str) -> str:
    """One nvidia-smi query, numbers only. Empty string when there is no GPU."""
    try:
        r = subprocess.run(["nvidia-smi", f"--query-{query}", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _mib(value: str) -> int | None:
    """An nvidia-smi memory field; None for '[N/A]' (Windows WDDM drivers report no per-process use)."""
    value = value.strip()
    return int(value) if value.isdigit() else None


def gpu_report(label: str = "") -> dict | None:
    """Three VRAM numbers; the diagnosis is in the gap between the last two.

      free          what is left on the card, for every process
      torch         what PyTorch's caching allocator holds
      this process  what the driver attributes to THIS Python process

    If "this process" is far above "torch", a library is holding VRAM outside PyTorch
    (JAX, typically) and `free_gpu()` won't get it back. If "free" shrank while both
    stayed put, another process grew (Ollama loading a model). None without a GPU.
    """
    total_free = _nvidia("gpu=memory.total,memory.free")
    if not total_free:
        return None
    total, free = (int(x) for x in total_free.split(", ")[:2])
    mine = None
    for line in _nvidia("compute-apps=pid,used_gpu_memory").splitlines():
        fields = [x.strip() for x in line.split(",")]
        if len(fields) == 2 and fields[0] == str(os.getpid()):
            mine = _mib(fields[1])
    torch_gb = 0.0
    try:
        import torch

        if torch.cuda.is_available():
            torch_gb = torch.cuda.memory_reserved() / 1e9
    except ImportError:
        pass
    report = {"total_mib": total, "free_mib": free, "torch_reserved_gb": round(torch_gb, 2),
              "this_process_mib": mine}
    print(f"   [vram] {label:<24} free {free:>6} MiB · torch {torch_gb:4.1f} GB · "
          f"this process {mine if mine is not None else '?':>6} MiB")
    return report


def free_gpu() -> None:
    """Give back the VRAM PyTorch's allocator is caching. Call before loading a model.

    PyTorch keeps what it frees: after embedding a corpus it can sit on several GB it no
    longer uses. Ollama, a different process, sees that memory as taken and offloads
    layers of the generator to the CPU -- same answers, ~10x slower, no error.
    """
    import gc

    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        before = torch.cuda.memory_reserved() / 1e9
        torch.cuda.empty_cache()
        print(f"   [vram] torch held {before:.1f} GB, now {torch.cuda.memory_reserved() / 1e9:.1f} GB")


def gpu_orphans(threshold_mib: int = 2000) -> list[tuple[int, str, int]]:
    """Processes other than this one holding GPU memory, as (pid, name, MiB).

    After a Colab runtime RESTART the previous kernel's model runner can survive and keep
    its VRAM; the new kernel doesn't see it. Warns when the orphans exceed `threshold_mib`.
    """
    orphans = []
    for line in _nvidia("compute-apps=pid,process_name,used_gpu_memory").splitlines():
        fields = [x.strip() for x in line.split(", ")]
        if len(fields) == 3 and fields[0].isdigit() and int(fields[0]) != os.getpid():
            mib = _mib(fields[2])
            if mib is not None:
                orphans.append((int(fields[0]), fields[1], mib))
    held = sum(m for _, _, m in orphans)
    if held > threshold_mib:
        print("=" * 76)
        print(f"THE GPU IS ALREADY OCCUPIED by other processes: {held} MiB.")
        print("Almost always an orphan from a previous runtime. Restarting does NOT clear it:")
        print("  Runtime -> Disconnect and delete runtime, then start again.")
        print("=" * 76)
    return orphans


def process_ram_gb() -> float:
    """Resident memory of this process, in GB (NaN without psutil)."""
    try:
        import psutil
    except ImportError:
        return float("nan")
    return psutil.Process(os.getpid()).memory_info().rss / 1e9


def diagnostics() -> dict:
    """What this runtime is: OS, Python, torch, GPU, RAM, and the wiring above."""
    info = {
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "interpreter": sys.executable,
        "colab": on_colab(),
        "logical_cores": os.cpu_count(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
            info["gpu_memory_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2)
    except ImportError:
        info["torch"] = "not installed"
    try:
        import psutil

        vm = psutil.virtual_memory()
        info["ram_total_gb"] = round(vm.total / 1e9, 1)
        info["ram_free_gb"] = round(vm.available / 1e9, 1)
    except ImportError:
        pass
    info["HF_HOME"] = os.environ.get("HF_HOME")
    info["jax_guard"] = (os.environ.get("XLA_PYTHON_CLIENT_PREALLOCATE") == "false"
                         and os.environ.get("JAX_PLATFORMS") == "cpu")
    info["ca_bundle"] = str(CA_BUNDLE) if CA_BUNDLE_ACTIVE else "not present (normal)"
    if ARTIFACTS.is_symlink():
        info["artifacts"] = f"-> {os.readlink(ARTIFACTS)} (Drive)"
    else:
        info["artifacts"] = f"{ARTIFACTS} (local disk)"
    return info


def summary() -> None:
    """Print the diagnostics, readably."""
    info = diagnostics()
    width = max(len(k) for k in info)
    print("=" * 66)
    print("ENVIRONMENT")
    print("=" * 66)
    for k, v in info.items():
        print(f"{k:<{width}} : {v}")
    if not info.get("cuda_available", False):
        print("-" * 66)
        print("No NVIDIA GPU: fine for SMOKE_TEST = True on CPU. The full profile needs a T4.")
    print("=" * 66)


if __name__ == "__main__":
    summary()
