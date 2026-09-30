"""
The generator, through Ollama's native REST API: server lifecycle, token counting, and a
chat call that tells you what the server actually did with your prompt.

    import llm
    llm.setup("qwen3:8b", num_ctx=8192)                 # install (Colab), serve, pull, probe
    r = llm.chat([{"role": "user", "content": "..."}], model="qwen3:8b", num_ctx=8192)
    r.text, r.prompt_tokens, r.done_reason, r.error

Public API:
    OLLAMA_VERSION, HOST, SERVER_LOG, HF_TOKENIZERS, KNOWN_DIGESTS, STATS,
    ChatResult, LLMError, ContextOverflow, CallCache,
    ollama_bin, server_alive, server_version, install_ollama, ensure_server, pull, model_digest,
    unload, placement, probe_thinking, probe_key_order, setup,
    count_prompt_tokens, count_tokens, calibrate,
    use_cache, chat, ask, structured, extract_json

FACTS THIS MODULE IS BUILT AROUND
---------------------------------
Server behaviour changes between Ollama versions. These were reproduced on Ollama 0.34.4
(OLLAMA_VERSION) with qwen3:1.7b and qwen3:8b, on 2026-09-28: default context 4,096; a
5,151-token prompt at num_ctx 2,048 accepted silently, 1,026 tokens evaluated, the
instruction at its head lost; a 3,387-token history cut to 2,004, the first turn's fact
lost; `truncate: false` refused with HTTP 400; a num_ctx change cost an 11 s reload; keys
written in declaration order; prompt_eval_count including cached tokens. `setup()` warns
when the running server differs; the probes below (`probe_thinking`, `probe_key_order`,
`calibrate`) measure thinking, key order and the template offset on YOUR server. What a
prompt that doesn't fit does (fact 3) is not probed: `chat()` catches it call by call
(ContextOverflow before sending, SILENT_TRUNCATION after), and `strict_ctx=False` lets you
watch it happen once, on purpose.

1. The chat API is STATELESS. Every call sends the whole conversation; the model keeps
   nothing between calls. Whatever "memory" your system has is what you put in `messages`.
2. The context window is a per-request setting: `options.num_ctx`. If you don't send it,
   the server uses its default -- 4,096 tokens on a T4 (recent versions pick the default
   from the GPU's memory, 4,096 below ~24 GiB; earlier ones used a fixed default). The online
   Modelfile reference still says 2,048: measure, don't trust the doc. The
   OpenAI-compatible `/v1` endpoint can't set num_ctx per request, so anything pointed at
   it gets the server default -- unless you bake num_ctx into a derived model (a Modelfile
   with `PARAMETER num_ctx 8192` + `ollama create`).
3. When the prompt doesn't fit, NOTHING FAILS -- by default:
   - through /api/chat, the server drops the OLDEST messages (keeping the system message
     and the latest ones), logged at DEBUG level only;
   - a single oversized prompt is cut: its first few tokens and its TAIL survive, the
     middle is discarded -- your instructions and top-ranked passages go, the question
     at the end survives. Logged once, at WARN, in a server log nobody reads (this module
     writes it to SERVER_LOG instead of throwing it away);
   - a prompt that fits but leaves less room than the reply needs is NOT truncated: mid-
     answer the server shifts the window (drops the older half of the context after the
     first few tokens) and keeps generating. prompt_eval_count matches your count, so only
     checking prompt + num_predict <= num_ctx BEFORE sending catches it.
   The model answers fluently either way. The API can be told to refuse instead
   (`"truncate": false` -> HTTP 400; `"shift": false` -> stop instead of sliding the
   window mid-answer): chat() sends both when strict_ctx=True, and ALSO counts the prompt
   itself before sending, so an overflow never reaches the server unnoticed.
4. Changing `num_ctx` (or other load-time options) between calls RELOADS the model.
   Nothing fails; every call just pays a reload. Keep it constant within an experiment.
5. Structured output (`format=<JSON schema>`) constrains decoding to the schema. The order
   the keys are WRITTEN in -- which decides whether the model reasons before or after it
   answers -- has differed between versions: the current grammar follows the schema's
   property order (required fields first, then optional ones), and some servers have
   emitted keys sorted alphabetically. Declare the reasoning field first, keep it
   required, and give it a name that also sorts first; `probe_key_order()` tells you what
   your server does. The grammar guarantees shape, not completion: a reply cut by
   `num_predict` (`done_reason == "length"`) is invalid JSON.
6. The `qwen3:4b` tag is Qwen3-4B-Thinking-2507 (thinking-only), not the hybrid sibling of
   `qwen3:8b` (that one is `qwen3:4b-q4_K_M`). `probe_thinking()` checks what a tag does
   with `think=False`.
7. On a thinking-capable model the server turns thinking ON when the request doesn't say
   otherwise, and returns the reasoning in `message.thinking`: output tokens spent, and
   discarded by any client that reads only `content`. With `think=False`, qwen3 has been
   reported to leak reasoning into `content`, closed by `</think>` -- not seen on 0.34.4
   (0 leaks in about 700 calls with qwen3:1.7b and qwen3:8b). It is stripped here and
   COUNTED anyway (STATS["think_leaks"]), because text that reaches a memory store or a
   summary verbatim is stored as if the user had said it.

Talks to the server with `requests`, not the `ollama` client library, so every field of
the response (done_reason, prompt_eval_count, load_duration, ...) is visible.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from store import append_jsonl, read_jsonl, sha256_json

# The server version the FACTS above were checked against. `setup()` warns when the running
# server differs; on Colab, `install_ollama()` installs exactly this one.
OLLAMA_VERSION = "0.34.4"


def _host() -> str:
    """OLLAMA_HOST as a client URL: a scheme, a connectable address, and a port."""
    raw = os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434"
    parts = urlsplit(raw if "://" in raw else "http://" + raw)
    host = parts.hostname
    if host in (None, "", "0.0.0.0", "::"):  # a bind-all address is not one a client can dial
        host = "127.0.0.1"
    return f"{parts.scheme}://{host}:{parts.port or 11434}"


HOST = _host()
SERVER_LOG = Path(tempfile.gettempdir()) / "ollama_serve.log"

# Ollama tag -> the HuggingFace repo whose tokenizer and chat template match it. Used to
# count prompt tokens BEFORE sending, so an overflow is caught instead of truncated.
# Quantization variants resolve by prefix ("qwen3:8b-q4_K_M" -> "qwen3:8b"). Add the tags
# you use: without an entry, the ContextOverflow / SILENT_TRUNCATION guards are off.
HF_TOKENIZERS = {
    "qwen3:0.6b": "Qwen/Qwen3-0.6B",
    "qwen3:1.7b": "Qwen/Qwen3-1.7B",
    "qwen3:4b-q4_K_M": "Qwen/Qwen3-4B",
    "qwen3:4b-instruct-2507": "Qwen/Qwen3-4B-Instruct-2507",
    "qwen3:8b": "Qwen/Qwen3-8B",
    "qwen3:14b": "Qwen/Qwen3-14B",
}

# Digests observed for tags we rely on. A different digest means the tag now points at a
# different model file -- results are no longer comparable with earlier runs.
KNOWN_DIGESTS = {"qwen3:8b": "500a1f067a9f"}

STATS: dict[str, int] = {
    "calls": 0, "cache_hits": 0, "errors": 0, "prompt_tokens": 0, "output_tokens": 0,
    "silent_truncations": 0, "server_refusals": 0, "output_truncations": 0,
    "think_leaks": 0, "reloads": 0,
}


class LLMError(RuntimeError):
    """The server can't be reached or refused the request."""


class ContextOverflow(LLMError):
    """The prompt plus the output reserve does not fit in num_ctx. Raised BEFORE sending."""


@dataclass
class ChatResult:
    text: str = ""
    thinking: str = ""
    done_reason: str | None = None
    prompt_tokens: int | None = None        # prompt_eval_count, as the server reports it
    cached_tokens: int | None = None        # prompt_eval_cached_count, on servers that report it
    expected_prompt_tokens: int | None = None  # our own count, from the chat template
    output_tokens: int | None = None
    ms: float | None = None
    load_ms: float | None = None
    model: str = ""
    digest: str | None = None
    think_leak: bool = False
    cached: bool = False
    error: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def ok(self) -> bool:
        return self.error is None and self.done_reason == "stop"

    @property
    def truncated(self) -> bool:
        """The OUTPUT was cut by num_predict."""
        return self.done_reason == "length"

    def log(self) -> dict:
        """The fields worth keeping in a results row."""
        d = asdict(self)
        for k in ("raw", "text", "thinking"):
            d.pop(k, None)
        return d


# --- server lifecycle -------------------------------------------------------------------------
def server_alive(timeout: float = 2) -> bool:
    try:
        return requests.get(f"{HOST}/api/tags", timeout=timeout).ok
    except requests.exceptions.RequestException:
        return False


def server_version() -> str | None:
    try:
        return requests.get(f"{HOST}/api/version", timeout=5).json().get("version")
    except (requests.exceptions.RequestException, ValueError):
        return None


def ollama_bin() -> str | None:
    """The `ollama` executable: on PATH, or where the Windows installer puts it.

    The Windows installer puts it in %LOCALAPPDATA%/Programs/Ollama and is supposed to add
    that folder to PATH -- which doesn't always happen (a policy-managed machine, a
    terminal opened before the install). The server still runs; only the command is missing.
    """
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _on_colab() -> bool:
    return "google.colab" in sys.modules or bool(os.environ.get("COLAB_RELEASE_TAG"))


def install_ollama(version: str = OLLAMA_VERSION) -> None:
    """Install the Ollama server on a Linux VM (Colab). No-op if it's already installed.

    On Windows/macOS install it from https://ollama.com/download instead; this raises there.
    """
    if ollama_bin():
        return
    if platform.system() != "Linux":
        raise LLMError("Ollama is not installed. Install it from https://ollama.com/download "
                       "and make sure `ollama` is on PATH, then re-run.")
    print(f"installing Ollama {version} (about a minute) ...")
    if shutil.which("apt-get"):
        # The installer ships a .tar.zst: without zstd it fails halfway.
        subprocess.run("apt-get -qq update && apt-get -qq install -y zstd", shell=True,
                       check=False, stdout=subprocess.DEVNULL)
    subprocess.run(f"curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION={version} sh",
                   shell=True, check=True, stdout=subprocess.DEVNULL)
    if not ollama_bin():
        raise LLMError("the Ollama installer finished but `ollama` is not on PATH")


def _server_env() -> dict:
    env = dict(os.environ)
    env.setdefault("OLLAMA_HOST", HOST.split("://", 1)[1])
    # One request at a time and one resident model: the KV-cache size stays predictable,
    # and no second model sits in VRAM that the embedder or the reranker needs.
    env.setdefault("OLLAMA_NUM_PARALLEL", "1")
    env.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
    env.setdefault("OLLAMA_KEEP_ALIVE", "30m")
    return env


def ensure_server(wait_s: int = 60) -> None:
    """Make sure a server answers on HOST, starting one if needed. Raises LLMError if it can't.

    A server started here writes its log to SERVER_LOG -- the only place a "truncating input
    prompt" warning or an out-of-memory error ever shows up.
    """
    if server_alive():
        return
    binary = ollama_bin()
    if not binary:
        raise LLMError("Ollama is not installed (on Colab: llm.install_ollama()).")
    if _on_colab():
        # A dead server can leave its model runner alive, still holding VRAM. The new
        # server doesn't see it, finds the card full, and loads on the CPU: ~25 -> ~3
        # tokens/s, no error. Sweep orphans first.
        subprocess.run(["pkill", "-9", "-x", "ollama"], check=False)
        time.sleep(2)
    log = open(SERVER_LOG, "ab")
    kwargs: dict[str, Any] = {"stdout": log, "stderr": subprocess.STDOUT, "env": _server_env()}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # Not cosmetic: without a new session the server shares the kernel's process group,
        # and interrupting a notebook cell (SIGINT) kills it too -- silently, until the next call.
        kwargs["start_new_session"] = True
    subprocess.Popen([binary, "serve"], **kwargs)
    for _ in range(wait_s):
        if server_alive():
            print(f"Ollama server up on {HOST} (log: {SERVER_LOG})")
            return
        time.sleep(1)
    raise LLMError(f"the Ollama server did not come up on {HOST} within {wait_s}s; see {SERVER_LOG}")


def model_digest(model: str) -> str | None:
    """First 12 hex chars of the local model's digest, or None if it isn't pulled."""
    try:
        tags = requests.get(f"{HOST}/api/tags", timeout=10).json().get("models", [])
    except (requests.exceptions.RequestException, ValueError):
        return None
    wanted = model if ":" in model else model + ":latest"
    for m in tags:
        if m.get("name") == wanted or m.get("model") == wanted:
            return (m.get("digest") or "")[:12] or None
    return None


def pull(model: str) -> str | None:
    """Download `model` if it isn't local; return its digest. Warns on an unexpected digest."""
    if model_digest(model) is None:
        print(f"pulling {model} ...")
        last = -10
        with requests.post(f"{HOST}/api/pull", json={"model": model, "stream": True},
                           stream=True, timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise LLMError(f"pull {model}: {msg['error']}")
                total, done = msg.get("total"), msg.get("completed")
                if total and done:
                    pct = int(100 * done / total)
                    if pct >= last + 10:
                        print(f"   {pct:3d}%  {done / 1e9:.2f}/{total / 1e9:.2f} GB")
                        last = pct
    digest = model_digest(model)
    _DIGESTS[model] = digest
    expected = KNOWN_DIGESTS.get(model)
    if expected and digest and not digest.startswith(expected):
        print(f"WARNING: {model} has digest {digest}, not the {expected} these facts were checked "
              "against. The tag now points at a different model file.", file=sys.stderr)
    return digest


def unload(model: str) -> None:
    """Evict `model` from memory now (instead of after keep_alive)."""
    try:
        requests.post(f"{HOST}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    except requests.exceptions.RequestException:
        pass
    _LAST_CTX.pop(model, None)


def placement(model: str) -> str:
    """Where the loaded model sits: '100% GPU', a CPU/GPU split, or 'not loaded'.

    A split means the model didn't fit in VRAM: same answers, several times slower, and
    no error. Check this after loading, and after anything else grabbed GPU memory.
    """
    try:
        loaded = requests.get(f"{HOST}/api/ps", timeout=10).json().get("models", [])
    except (requests.exceptions.RequestException, ValueError):
        return "server not reachable"
    for m in loaded:
        if m.get("name") == model or m.get("model") == model:
            size, vram = m.get("size") or 0, m.get("size_vram") or 0
            ctx = m.get("context_length")
            where = "CPU only" if vram == 0 else (
                "100% GPU" if vram >= size else f"SPLIT {100 * (size - vram) / size:.0f}% CPU / "
                f"{100 * vram / size:.0f}% GPU -- expect several times slower")
            return f"{model}: {where} · {size / 1e9:.1f} GB" + (f" · context {ctx}" if ctx else "")
    return f"{model}: not loaded"


# --- token counting ---------------------------------------------------------------------------
_TOKENIZERS: dict[str, Any] = {}
_WARNED_NO_TOKENIZER: set[str] = set()


def _hf_repo(model: str) -> str | None:
    """The tokenizer repo for a tag: exact match, else the longest mapped prefix + '-'."""
    if model in HF_TOKENIZERS:
        return HF_TOKENIZERS[model]
    for tag in sorted(HF_TOKENIZERS, key=len, reverse=True):
        if model.startswith(tag + "-"):
            return HF_TOKENIZERS[tag]
    return None


def _tokenizer(model: str):
    repo = _hf_repo(model)
    if repo is None:
        return None
    if repo not in _TOKENIZERS:
        from transformers import AutoTokenizer

        _TOKENIZERS[repo] = AutoTokenizer.from_pretrained(repo)
    return _TOKENIZERS[repo]


def count_prompt_tokens(messages: list[dict], model: str, *, think: bool = False) -> int | None:
    """Tokens this conversation occupies once the chat template is applied.

    `len(tokenizer(text))` UNDERCOUNTS: the template adds role markers and separators to
    every message, and the generation prompt at the end. And the tokenizer's
    `model_max_length` is 131,072 for Qwen3, so it will never warn you at 4,096.
    None if `model` has no tokenizer in HF_TOKENIZERS.
    """
    tok = _tokenizer(model)
    if tok is None:
        return None
    enc = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                  enable_thinking=think, return_dict=True)
    ids = enc["input_ids"]
    if ids and isinstance(ids[0], list):  # batched shape from some versions
        ids = ids[0]
    if not isinstance(ids, list) or (ids and not isinstance(ids[0], int)):
        raise TypeError(f"unexpected apply_chat_template output: {type(ids)}")
    return len(ids)


def count_tokens(text: str, model: str) -> int | None:
    """Tokens of a bare string (no template) under `model`'s tokenizer."""
    tok = _tokenizer(model)
    return None if tok is None else len(tok.encode(text, add_special_tokens=False))


# Measured by calibrate(): template-count minus server-count on prompts that fit, and
# whether prompt_eval_count includes tokens served from the prompt cache.
_OFFSET: dict[str, int] = {}
_COUNT_INCLUDES_CACHED: dict[str, bool] = {}


# --- the call ------------------------------------------------------------------------------------
class CallCache:
    """Append-only JSONL cache of successful calls, keyed by everything that determines them.

    At temperature 0 with a fixed seed, the same (server, model digest, messages, options)
    gives the same answer, so a re-run after a disconnect replays instead of re-generating.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: dict[str, dict] = {}
        if self.path.is_file():
            for row in read_jsonl(self.path):
                self._entries[row["key"]] = row["result"]

    def get(self, key: str) -> dict | None:
        return self._entries.get(key)

    def put(self, key: str, result: dict) -> None:
        self._entries[key] = result
        append_jsonl(self.path, {"key": key, "result": result})

    def __len__(self) -> int:
        return len(self._entries)


_CACHE: CallCache | None = None
_LAST_CTX: dict[str, int] = {}
_DIGESTS: dict[str, str | None] = {}
_SERVER: dict[str, str | None] = {}


def use_cache(path: str | Path | None) -> CallCache | None:
    """Turn the call cache on (a JSONL path, one per model is a good habit) or off (None)."""
    global _CACHE
    _CACHE = CallCache(path) if path is not None else None
    if _CACHE is not None:
        print(f"LLM call cache: {_CACHE.path} ({len(_CACHE)} entries)")
    return _CACHE


def _digest(model: str) -> str | None:
    if _DIGESTS.get(model) is None:  # never memoize "unknown": the model may be pulled later
        _DIGESTS[model] = model_digest(model)
    return _DIGESTS[model]


def _server() -> str | None:
    if _SERVER.get("version") is None:
        _SERVER["version"] = server_version()
    return _SERVER["version"]


def _strip_think(text: str) -> tuple[str, bool]:
    if "</think>" in text:
        return text.split("</think>")[-1].strip(), True
    if "<think>" in text:  # opened and never closed: nothing usable after it
        return text.split("<think>")[0].strip(), True
    return text.strip(), False


def chat(messages: list[dict], *, model: str, num_ctx: int, num_predict: int = 512,
         temperature: float = 0.0, seed: int = 0, think: bool = False,
         format: dict | str | None = None, keep_alive: str | int = "30m",
         strict_ctx: bool = True, cache: bool = True, retries: int = 1, timeout: int = 600,
         options: dict | None = None) -> ChatResult:
    """One chat call with explicit num_ctx, and a report of what the server did with it.

    - BEFORE sending: counts the prompt with the model's chat template. If prompt +
      num_predict exceeds num_ctx it raises ContextOverflow (strict_ctx=True), because the
      server would otherwise truncate without telling you. strict_ctx=True also asks the
      SERVER to refuse rather than truncate (error CONTEXT_OVERFLOW). strict_ctx=False
      sends it anyway, with the server's default behaviour -- that's how you watch the
      truncation happen.
    - AFTER: if the server evaluated clearly fewer prompt tokens than the template count,
      `error` is SILENT_TRUNCATION. A reply cut by num_predict has done_reason "length"
      (`.truncated`). Leaked reasoning is stripped and flagged.
    - Transport failures are retried once (after restarting the server) and then reported
      in `error`, never raised: one failed call must not kill a two-hour run.
    """
    opts = {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": temperature,
            "seed": seed, **(options or {})}
    result = ChatResult(model=model)
    try:
        expected = count_prompt_tokens(messages, model, think=think)
    except Exception as e:  # tokenizer download or template problem: don't block the call
        expected = None
        print(f"WARNING: could not count tokens for {model}: {type(e).__name__}: {e}", file=sys.stderr)
    if expected is None and model not in _WARNED_NO_TOKENIZER:
        _WARNED_NO_TOKENIZER.add(model)
        print(f"WARNING: no tokenizer for {model} in llm.HF_TOKENIZERS: the ContextOverflow and "
              "SILENT_TRUNCATION checks are OFF for it. Add its HuggingFace repo there.", file=sys.stderr)
    result.expected_prompt_tokens = expected
    if expected is not None and expected + num_predict > num_ctx:
        message = (f"prompt {expected} + num_predict {num_predict} = {expected + num_predict} "
                   f"> num_ctx {num_ctx}: the server would silently truncate it")
        if strict_ctx:
            raise ContextOverflow(message)
        print(f"WARNING (strict_ctx=False): {message}", file=sys.stderr)

    key = sha256_json({"model": model, "digest": _digest(model), "server": _server(),
                       "messages": messages, "options": opts, "think": think, "format": format,
                       "strict": strict_ctx, "v": 2})
    if cache and _CACHE is not None:
        hit = _CACHE.get(key)
        if hit is not None:
            STATS["cache_hits"] += 1
            res = ChatResult(**{**hit, "cached": True})
            STATS["think_leaks"] += res.think_leak
            STATS["output_truncations"] += res.truncated
            return res

    if model in _LAST_CTX and _LAST_CTX[model] != num_ctx:
        print(f"note: num_ctx for {model} changed {_LAST_CTX[model]} -> {num_ctx}; the server "
              "reloads the model (latency, not an error).", file=sys.stderr)
    _LAST_CTX[model] = num_ctx

    body: dict[str, Any] = {"model": model, "messages": messages, "stream": False,
                            "options": opts, "keep_alive": keep_alive, "think": think}
    if strict_ctx:
        body["truncate"] = False  # refuse (HTTP 400) instead of dropping messages / cutting the middle
        body["shift"] = False     # stop at the window instead of sliding it mid-answer
    if format is not None:
        body["format"] = format
    data: dict | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(f"{HOST}/api/chat", json=body, timeout=timeout)
            if r.status_code == 400 and "does not support thinking" in r.text and "think" in body:
                body.pop("think")  # a non-thinking model: there's nothing to switch off
                r = requests.post(f"{HOST}/api/chat", json=body, timeout=timeout)
            # The wording has varied ("exceeds the context length" / "exceeds the available
            # context size"): match the substance, not the sentence.
            if r.status_code == 400 and "exceeds" in r.text and "context" in r.text:
                STATS["calls"] += 1
                STATS["server_refusals"] += 1
                STATS["errors"] += 1
                result.error = f"CONTEXT_OVERFLOW (server): {r.text[:200]}"
                return result  # deterministic: restarting the server and resending won't help
            if not r.ok:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            break
        except (requests.exceptions.RequestException, LLMError, ValueError) as e:
            result.error = f"{type(e).__name__}: {str(e)[:300]}"
            if attempt < retries:
                try:
                    ensure_server()
                except LLMError:
                    pass
    STATS["calls"] += 1
    if data is None:
        STATS["errors"] += 1
        return result

    result.error = None
    result.raw = data
    msg = data.get("message") or {}
    result.text, result.think_leak = _strip_think(msg.get("content") or "")
    result.thinking = msg.get("thinking") or ""
    result.done_reason = data.get("done_reason")
    result.prompt_tokens = data.get("prompt_eval_count")
    result.cached_tokens = data.get("prompt_eval_cached_count")
    result.output_tokens = data.get("eval_count")
    result.ms = round(data.get("total_duration", 0) / 1e6, 1)
    result.load_ms = round(data.get("load_duration", 0) / 1e6, 1)
    result.digest = _digest(model)

    STATS["think_leaks"] += result.think_leak
    STATS["output_truncations"] += result.truncated
    STATS["reloads"] += (result.load_ms or 0) > 1000
    STATS["prompt_tokens"] += result.prompt_tokens or 0
    STATS["output_tokens"] += result.output_tokens or 0

    if expected is not None and result.prompt_tokens is not None:
        seen = result.prompt_tokens
        # Documented: prompt_eval_count counts ALL prompt tokens, cached ones included. Add the
        # cached count only if calibrate() MEASURED that this server excludes them.
        if result.cached_tokens and _COUNT_INCLUDES_CACHED.get(model) is False:
            seen += result.cached_tokens
        tolerance = max(16, int(0.02 * expected)) + abs(_OFFSET.get(model, 0))
        if seen < expected - tolerance:
            STATS["silent_truncations"] += 1
            result.error = (f"SILENT_TRUNCATION: the server evaluated {seen} prompt tokens, the "
                            f"template counts {expected}; part of the prompt never reached the model")
    if result.error:
        STATS["errors"] += 1
    elif cache and _CACHE is not None:
        _CACHE.put(key, result.log() | {"text": result.text, "thinking": result.thinking})
    return result


def ask(prompt: str, system: str | None = None, **kw) -> ChatResult:
    """One user message (and an optional system message). Same keywords as chat()."""
    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    return chat(messages, **kw)


def extract_json(text: str) -> Any:
    """The FIRST JSON value in `text`, tolerating code fences and prose around it.

    Not a greedy regex from the first '{' to the last '}': a model that answers twice
    produces two objects, and spanning both gives `Extra data`. `raw_decode` stops at the
    end of the first complete value.
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                value, _ = decoder.raw_decode(text, i)
                return value
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON value found")


def structured(messages: list[dict], schema: type, **kw):
    """chat() constrained to a pydantic `schema`. Returns (instance or None, ChatResult).

    Any call with `result.error` set returns None: a transport failure, a server refusal,
    or SILENT_TRUNCATION -- an answer to a prompt the model only partly saw is not an
    answer. A reply that doesn't parse sets PARSE_FAILED / TRUNCATED_JSON. Count all of
    these as their own category: never as abstentions, never as scored answers.
    """
    result = chat(messages, format=schema.model_json_schema(), **kw)
    if result.error:
        return None, result
    err: Exception | None = None
    for parse in (schema.model_validate_json, lambda t: schema.model_validate(extract_json(t))):
        try:
            return parse(result.text), result
        except Exception as e:
            err = e
    kind = "TRUNCATED_JSON" if result.truncated else "PARSE_FAILED"
    result.error = f"{kind}: {str(err)[:200]}"
    STATS["errors"] += 1
    return None, result


# --- probes ----------------------------------------------------------------------------------------
def probe_thinking(model: str, *, num_ctx: int) -> dict:
    """What `think=False` really does on this tag. Uses the caller's num_ctx (no reload)."""
    q = [{"role": "user", "content": "Reply with exactly one word: what is the capital of France?"}]
    off = chat(q, model=model, num_ctx=num_ctx, num_predict=256, think=False, cache=False)
    on = chat(q, model=model, num_ctx=num_ctx, num_predict=512, think=True, cache=False)
    failed = [r.error for r in (off, on) if r.error and not r.text]
    if failed:
        raise LLMError(f"thinking probe on {model} failed, nothing was measured: {failed[0]}")
    return {
        "honors_think_false": not off.thinking and not off.think_leak,
        "leaks_think_tag": off.think_leak,
        "thinking_only": bool(off.thinking),
        "supports_thinking": bool(on.thinking) or on.think_leak,
        "answer": off.text[:40],
    }


def probe_key_order(model: str, *, num_ctx: int) -> dict:
    """In which order does this server WRITE the keys of a structured reply?

    Sends a schema whose properties are declared "zeta" then "alfa" and looks at the reply.
    'declaration' means the model writes fields in the order you declare them; 'alphabetical'
    means name order decides. Either way: declare the reasoning field first AND name it so
    it sorts first, and you're covered.
    """
    schema = {"type": "object", "properties": {"zeta": {"type": "string"}, "alfa": {"type": "string"}},
              "required": ["zeta", "alfa"]}
    r = chat([{"role": "user", "content": "Fill both fields with one short word each."}], model=model,
             num_ctx=num_ctx, num_predict=64, format=schema, cache=False)
    z, a = r.text.find('"zeta"'), r.text.find('"alfa"')
    order = "unknown" if min(z, a) < 0 else ("declaration" if z < a else "alphabetical")
    return {"order": order, "reply": r.text[:80], "error": r.error}


def calibrate(model: str, *, num_ctx: int) -> dict:
    """Compare our template count with the server's prompt_eval_count on prompts that fit.

    Also sends one prompt twice, to learn whether prompt_eval_count includes tokens served
    from the prompt cache -- which decides how SILENT_TRUNCATION is detected.
    """
    prompts = ["Hola.", "Explicá en una oración qué es una ventana de contexto.",
               "Listá tres módulos de la biblioteca estándar de Python. " * 5]
    deltas = []
    for p in prompts:
        msgs = [{"role": "user", "content": p + f" [{time.time_ns()}]"}]  # unique: no cache reuse
        r = chat(msgs, model=model, num_ctx=num_ctx, num_predict=8, cache=False)
        if r.expected_prompt_tokens is not None and r.prompt_tokens is not None:
            deltas.append(r.expected_prompt_tokens - r.prompt_tokens)
    if deltas:
        _OFFSET[model] = int(round(sum(deltas) / len(deltas)))
    same = [{"role": "user", "content": "Describí un árbol en diez palabras. " * 20 + str(time.time_ns())}]
    first = chat(same, model=model, num_ctx=num_ctx, num_predict=8, cache=False)
    second = chat(same, model=model, num_ctx=num_ctx, num_predict=8, cache=False)
    includes = None
    if first.prompt_tokens and second.prompt_tokens is not None:
        includes = second.prompt_tokens >= first.prompt_tokens - 2
        _COUNT_INCLUDES_CACHED[model] = includes
    return {"template_minus_server": deltas, "offset": _OFFSET.get(model),
            "repeat_prompt_tokens": (first.prompt_tokens, second.prompt_tokens),
            "repeat_cached_tokens": (first.cached_tokens, second.cached_tokens),
            "prompt_eval_count_includes_cached": includes}


def setup(model: str, *, num_ctx: int, pull_model: bool = True, probe: bool = True) -> dict:
    """Everything before the first real call: install (Colab), serve, pull, probe, place.

    Raises if `think=False` isn't honoured by this tag -- every experiment here assumes a
    direct answer, and a thinking-only model spends num_predict on reasoning.
    """
    if _on_colab():
        install_ollama()
    ensure_server()
    version = server_version()
    if version and version != OLLAMA_VERSION:
        print(f"WARNING: Ollama server {version}; the facts in llm.py were checked on "
              f"{OLLAMA_VERSION}. The probes below measure the ones that matter.", file=sys.stderr)
    digest = pull(model) if pull_model else model_digest(model)
    info: dict[str, Any] = {"model": model, "digest": digest, "server": version, "num_ctx": num_ctx}
    if probe:
        info["thinking"] = probe_thinking(model, num_ctx=num_ctx)
        if not info["thinking"]["honors_think_false"]:
            raise LLMError(f"{model} does not honour think=False: {info['thinking']}. Use a hybrid "
                           "tag (e.g. qwen3:8b), not a thinking-only one (the bare qwen3:4b tag).")
        info["key_order"] = probe_key_order(model, num_ctx=num_ctx)
        if _hf_repo(model):
            info["calibration"] = calibrate(model, num_ctx=num_ctx)
    info["placement"] = placement(model)
    for k, v in info.items():
        print(f"   {k:<12} {v}")
    return info


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Probe a local Ollama model.")
    ap.add_argument("--probe", metavar="MODEL", help="setup + thinking/key-order probes + calibration")
    ap.add_argument("--num-ctx", type=int, default=4096)
    args = ap.parse_args()
    if args.probe:
        setup(args.probe, num_ctx=args.num_ctx)
        print("STATS", STATS)
    else:
        ap.print_help()
