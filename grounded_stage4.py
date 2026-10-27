"""Etapa 4: respuestas fundamentadas con un presupuesto verificado.

El notebook 04_grounded_answers incluye una copia de este módulo, así puede abrirse solo
en Colab (igual que la Etapa 3). Las Etapas 5 y 6 pueden importarlo desde el repo:

    from grounded_stage4 import GroundedAnswer, assemble, build_messages, fit_prompt

Qué contiene:
  - GroundedAnswer: el schema de salida (razonamiento primero, en orden de declaración Y
    alfabético), con el booleano de abstención y las citas.
  - assemble / render_passages / build_messages / fit_prompt: el ensamblador. Saltea un
    pasaje que no entra y sigue con el siguiente (nunca `break`), y verifica el prompt
    completo con la plantilla de chat antes de mandar.
  - score_answer: puntaje sin juez (abstención por booleano, citas contra lo entregado,
    citas contra gold, contención de la clave, veredicto sí/no aparte, flags de
    consistencia). Un error es su propia categoría: nunca abstención, nunca puntuado.
  - two_by_two, summarize_arm, paired_comparison, bootstrap_mean: tablas y cotas de ruido.
  - find_stage3_run / load_stage3_run: lectura de la Etapa 3 verificando su procedencia.

No modifica la evaluación congelada ni los artefactos de la Etapa 3.
"""
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Literal
import hashlib
import json
import math
import random
import re
import unicodedata

from pydantic import BaseModel, Field


# --- configuración ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage4Config:
    """Todo lo que decide qué significa una fila de resultados (va al run_spec)."""
    model: str = "qwen3:8b"
    num_ctx: int = 8192            # fijo en todo el experimento: cambiarlo recarga el modelo
    num_predict: int = 700         # reserva de salida; el prompt tiene que entrar en num_ctx - num_predict
    safety_margin: int = 64        # margen sobre la cuenta propia antes de que llm.chat verifique
    passage_budget: int = 2500     # tokens de Qwen3 para el bloque de pasajes: el mismo de la Etapa 3
    temperature: float = 0.0
    seed: int = 0
    think: bool = False
    bootstrap_samples: int = 2000
    bootstrap_seed: int = 1337

    def __post_init__(self):
        if self.num_predict <= 0 or self.num_ctx <= self.num_predict:
            raise ValueError("num_ctx tiene que ser mayor que num_predict.")
        if self.passage_budget >= self.prompt_limit:
            raise ValueError("El presupuesto de pasajes no deja lugar para sistema y pregunta.")
        if self.temperature != 0.0 or self.think:
            raise ValueError("La etapa fija temperatura 0 y think=False.")

    @property
    def prompt_limit(self) -> int:
        """Tope del prompt completo según NUESTRA cuenta (plantilla incluida)."""
        return self.num_ctx - self.num_predict - self.safety_margin


# --- schema de salida ------------------------------------------------------------------------
class GroundedAnswer(BaseModel):
    # Declarados en el orden en que el modelo debería escribirlos, todos obligatorios, y con
    # nombres cuyo orden alfabético coincide ("analysis" < "answer" < "can_answer" <
    # "citations" < "verdict"): el razonamiento queda primero en cualquier servidor.
    analysis: str = Field(max_length=600, description="razonamiento breve: qué pasaje responde y por qué")
    answer: str = Field(max_length=1200, description="respuesta final, breve, en español")
    can_answer: bool = Field(description="false si el contexto no alcanza para responder")
    citations: list[str] = Field(description="section_id de los pasajes usados, copiados del marcador")
    verdict: Literal["si", "no", "no_aplica"] = Field(description="para preguntas de sí/no; si no, no_aplica")


def check_schema_order(schema: type[BaseModel] = GroundedAnswer) -> list[str]:
    """Falla si el campo de razonamiento no queda primero en declaración y en orden alfabético."""
    props = list(schema.model_json_schema()["properties"])
    required = schema.model_json_schema().get("required", [])
    if props[0] != "analysis" or sorted(props)[0] != "analysis":
        raise AssertionError(f"El razonamiento tiene que ir primero: {props}")
    if set(required) != set(props):
        raise AssertionError(f"Todos los campos deben ser obligatorios: {required} vs {props}")
    return props


# --- prompts ---------------------------------------------------------------------------------
SYSTEM_GROUNDED = """Sos un asistente que responde preguntas sobre un corpus de leyes argentinas.
Respondé usando EXCLUSIVAMENTE los pasajes que se te entregan, delimitados por marcadores
de la forma [doc_id · section_id]. No uses conocimiento propio ni completes con suposiciones.

Devolvé un objeto JSON con estos campos, en este orden:
- analysis: dos o tres oraciones. Indicá qué pasaje contiene la respuesta y qué dice. Si
  ninguno la contiene, decilo.
- answer: la respuesta, breve y directa, en español. Copiá cifras, plazos, fechas y nombres
  tal como aparecen en el pasaje. Si la pregunta es de sí o no, empezá con "Sí" o "No".
  Si los pasajes no alcanzan, escribí exactamente: "No hay información suficiente en los
  pasajes para responder."
- can_answer: true solo si los pasajes contienen la respuesta; false en caso contrario.
- citations: la lista de section_id de los pasajes que usaste, copiados exactamente del
  marcador (por ejemplo, LEY-24240#ART-4). Lista vacía si can_answer es false.
- verdict: "si" o "no" si la pregunta se responde con sí o no; "no_aplica" en otro caso."""

SYSTEM_CLOSED_BOOK = """Sos un asistente que responde preguntas sobre leyes argentinas.
No se te entrega ningún pasaje: respondé solo con lo que sepas. Si no lo sabés con
seguridad, o la pregunta depende de un documento o de datos particulares que no tenés,
no adivines.

Devolvé un objeto JSON con estos campos, en este orden:
- analysis: dos o tres oraciones sobre qué sabés del tema y qué tan seguro estás.
- answer: la respuesta, breve y directa, en español. Si la pregunta es de sí o no, empezá
  con "Sí" o "No". Si no podés responder, escribí exactamente: "No tengo información
  suficiente para responder."
- can_answer: true solo si podés responder; false en caso contrario.
- citations: lista vacía (no tenés pasajes para citar).
- verdict: "si" o "no" si la pregunta se responde con sí o no; "no_aplica" en otro caso."""

SEPARATOR = "\n\n"


def passage_block(p: dict) -> str:
    """Marcador [doc_id · section_id] + el texto con su prefijo (doc_id | título de sección).

    Es el bloque de la Etapa 3 sin el chunk_id: el modelo cita section_id, que es el nivel
    del gold. Varios hijos de una misma sección comparten marcador.
    """
    return f"[{p['doc_id']} · {p['section_id']}]\n{p['index_text']}"


def render_passages(passages: list[dict]) -> str:
    return SEPARATOR.join(passage_block(p) for p in passages)


def user_message(question: str, passages: list[dict] | None) -> str:
    """Pasajes primero, pregunta al final. passages=None -> libro cerrado (sin bloque)."""
    if passages is None:
        return f"PREGUNTA: {question}"
    body = render_passages(passages) if passages else "(no se entregó ningún pasaje)"
    return f"PASAJES:\n{body}\n\nPREGUNTA: {question}"


def build_messages(system: str, question: str, passages: list[dict] | None,
                   history: list[dict] | None = None) -> list[dict]:
    """Sistema + historial (Etapas 5/6) + el turno actual con sus pasajes."""
    return ([{"role": "system", "content": system}] + list(history or [])
            + [{"role": "user", "content": user_message(question, passages)}])


# --- el ensamblador --------------------------------------------------------------------------
def assemble(passages: list[dict], budget: int, count: Callable[[str], int],
             render: Callable[[list[dict]], str] = render_passages) -> tuple[list[dict], list[dict], int]:
    """Llena `budget` tokens con pasajes en el orden dado. Devuelve (entregados, salteados, usados).

    Un pasaje que no entra se saltea y se registra, y se sigue con el siguiente: un `break`
    en el primero que no entra descartaría también los más chicos que vienen después.
    `count` cuenta texto pelado (llm.count_tokens): la suma por bloque se verifica al final
    contra la cuenta del bloque renderizado completo, por si un borde de BPE agrega tokens.
    """
    if budget <= 0:
        raise ValueError("budget tiene que ser positivo")
    sep = count(SEPARATOR)
    delivered, skipped, used = [], [], 0
    for p in passages:
        n = count(passage_block(p)) + (sep if delivered else 0)
        if used + n > budget:
            skipped.append(p)
            continue
        delivered.append(p)
        used += n
    actual = count(render(delivered)) if delivered else 0
    while delivered and actual > budget:   # raro: la suma subestimó por bordes de tokens
        skipped.insert(0, delivered.pop())
        actual = count(render(delivered)) if delivered else 0
    return delivered, skipped, actual


@dataclass
class FittedPrompt:
    messages: list[dict]
    delivered: list[dict]
    skipped_ids: list[str]
    passage_tokens: int                 # cuenta del bloque de pasajes renderizado (texto pelado)
    expected_prompt_tokens: int | None  # cuenta con la plantilla de chat (llm.count_prompt_tokens)
    prompt_limit: int

    @property
    def fits(self) -> bool:
        return self.expected_prompt_tokens is None or self.expected_prompt_tokens <= self.prompt_limit


def fit_prompt(system: str, question: str, candidates: list[dict] | None, cfg: Stage4Config,
               count: Callable[[str], int], count_messages: Callable[[list[dict]], int | None],
               history: list[dict] | None = None, passage_budget: int | None = None) -> FittedPrompt:
    """Ensambla y cuenta el prompt COMPLETO con la plantilla. Si no entra, saca el último pasaje.

    candidates=None es libro cerrado. El presupuesto de pasajes es fijo (comparable entre
    filas); el tope del prompt completo es num_ctx - num_predict - margen.
    """
    budget = cfg.passage_budget if passage_budget is None else passage_budget
    if candidates is None:
        delivered, skipped, used = [], [], 0
    else:
        delivered, skipped, used = assemble(candidates, budget, count)
    skipped_ids = [p.get("chunk_id", p["section_id"]) for p in skipped]
    while True:
        msgs = build_messages(system, question, None if candidates is None else delivered, history)
        expected = count_messages(msgs)
        if expected is None or expected <= cfg.prompt_limit or not delivered:
            break
        removed = delivered.pop()
        skipped_ids.append(removed.get("chunk_id", removed["section_id"]))
        used = count(render_passages(delivered)) if delivered else 0
    return FittedPrompt(msgs, delivered, skipped_ids, used, expected, cfg.prompt_limit)


# --- normalización y puntaje sin juez ----------------------------------------------------------
def normalize_answer(text: str) -> str:
    """La misma normalización de la Etapa 3: minúsculas, sin acentos, sin '(12)', sin
    separadores de miles, sin puntuación. 'Ley 24.240' -> 'ley 24240'; '1,5' -> '1 5'
    (igual en la clave y en la respuesta, así que las comas decimales coinciden)."""
    text = unicodedata.normalize("NFD", (text or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"\(\s*\d+\s*\)", " ", text)
    text = re.sub(r"(?<=\d)[.,\s](?=\d{3}(?:\D|$))", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def contains_key(text: str, keys: list[str] | None) -> bool:
    normalized = f" {normalize_answer(text)} "
    return any(bool(normalize_answer(k)) and f" {normalize_answer(k)} " in normalized for k in keys or [])


def normalize_citation(c: str) -> str:
    """'[LEY-24240 · LEY-24240#ART-4]', 'LEY-24240 · LEY-24240#ART-4' -> 'LEY-24240#ART-4'."""
    c = (c or "").strip().strip("[]()").strip()
    parts = [x.strip() for x in re.split(r"\s*[·|]\s*", c) if x.strip()]
    with_hash = [x for x in parts if "#" in x]
    return (with_hash[0] if with_hash else (parts[-1] if parts else "")).strip("[]").strip()


# Solo para FLAGS de consistencia (inspección manual): la abstención se puntúa con el booleano.
_ABSTAIN_TEXT = re.compile(
    r"\b(no hay (informacion|datos|suficiente)|informacion (insuficiente|suficiente)|"
    r"no (tengo|dispongo de|cuento con) (informacion|datos)|no (es posible|puedo) (responder|determinar|saber)|"
    r"no (se )?(menciona|especifica|indica|encuentra|figura|aparece)|no lo se|no se puede determinar)\b")


def looks_like_abstention(answer: str) -> bool:
    return bool(_ABSTAIN_TEXT.search(normalize_answer(answer)))


ERROR = "error"
ABSTAINED = "abstained"
ANSWERED = "answered"


def score_answer(item: dict, answer: GroundedAnswer | None, error: str | None,
                 delivered: list[dict], closed_book: bool = False) -> dict:
    """Métricas de una respuesta. `item` es una fila de single_turn.jsonl.

    - error (r.error, ContextOverflow, PARSE_FAILED...): outcome 'error', nada más se puntúa.
    - abstención: SOLO el booleano can_answer.
    - correct: con respuesta -> respondió + clave contenida (+ veredicto si es sí/no);
      sin respuesta (fuera del corpus) -> se abstuvo.
    """
    gold = {(g["doc_id"], g.get("section_id")) for g in item.get("gold") or []}
    gold_sections = {s for _, s in gold if s}
    gold_docs_whole = {d for d, s in gold if s is None}
    keys = item.get("answer_key")
    answerable = bool(item.get("answerable", True))
    delivered_sections = {p["section_id"] for p in delivered}
    m: dict = {
        "answerable": answerable,
        "n_passages": len(delivered),
        # Libro cerrado no recibe pasajes: sus métricas de entrega no aplican (None, no 0).
        "gold_delivered": (any((p["doc_id"], p["section_id"]) in gold or p["doc_id"] in gold_docs_whole
                               for p in delivered) if answerable and not closed_book else None),
        "answer_delivered": (any(contains_key(p.get("text", ""), keys) for p in delivered)
                             if answerable and keys and not closed_book else None),
    }
    if error is not None or answer is None:
        m.update(outcome=ERROR, error=error or "sin respuesta parseada", correct=None)
        return m
    abstained = not answer.can_answer
    cited = [normalize_citation(c) for c in answer.citations]
    cited = [c for c in cited if c]
    delivered_fold = {s.casefold() for s in delivered_sections}
    invalid = [c for c in cited if c.casefold() not in delivered_fold]
    cited_gold = any(c.casefold() in {s.casefold() for s in gold_sections}
                     or c.split("#")[0].casefold() in {d.casefold() for d in gold_docs_whole} for c in cited)
    key_hit = contains_key(answer.answer, keys) if answerable and keys else None
    expected_verdict = item.get("expected_verdict")
    verdict_ok = None
    if expected_verdict:
        verdict_ok = {"yes": "si", "no": "no"}[expected_verdict] == answer.verdict
    if answerable:
        correct = (not abstained) and bool(key_hit) and (verdict_ok is not False)
    else:
        correct = abstained
    text_abstains = looks_like_abstention(answer.answer)
    m.update(
        outcome=ABSTAINED if abstained else ANSWERED,
        error=None,
        can_answer=answer.can_answer,
        correct=correct,
        key_hit=key_hit,
        expected_verdict=expected_verdict,
        verdict=answer.verdict,
        verdict_ok=verdict_ok,
        citations=cited,
        n_citations=len(cited),
        invalid_citations=invalid,
        cited_not_delivered=bool(invalid),
        cited_gold=cited_gold if answerable else None,
        abstained_with_answer_in_context=(abstained and bool(m["answer_delivered"] or m["gold_delivered"])
                                          if answerable and not closed_book else None),
        # Flags (heurísticos, para abrir la caja; no cambian ningún puntaje):
        flag_says_cannot_but_answers=abstained and (bool(key_hit) or not text_abstains),
        flag_says_can_but_abstains=(not abstained) and text_abstains,
        flag_answers_without_citation=(not abstained) and not cited and not closed_book,
    )
    return m


# --- tablas y estadística --------------------------------------------------------------------
def bootstrap_mean(values: list[float], seed: int = 1337, samples: int = 2000):
    if not values:
        return None, None
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(samples))
    return means[int(0.025 * (samples - 1))], means[int(0.975 * (samples - 1))]


def _rate(rows: list[dict], key: str, where: Callable[[dict], bool] = lambda r: True):
    vals = [r["metrics"].get(key) for r in rows if where(r) and r["metrics"].get(key) is not None]
    return (sum(bool(v) for v in vals) / len(vals) if vals else None), len(vals)


def summarize_arm(rows: list[dict], cfg: Stage4Config) -> dict:
    """Una fila de la tabla de la etapa. Los errores se cuentan aparte y no se puntúan."""
    scored = [r for r in rows if r["metrics"]["outcome"] != ERROR]
    ans = [r for r in scored if r["metrics"]["answerable"]]
    ooc = [r for r in scored if not r["metrics"]["answerable"]]
    correct = [float(r["metrics"]["correct"]) for r in scored]
    lo, hi = bootstrap_mean(correct, cfg.bootstrap_seed, cfg.bootstrap_samples)
    llm_rows = [r.get("llm") or {} for r in rows]
    deltas = [l["expected_prompt_tokens"] - l["prompt_tokens"] for l in llm_rows
              if l.get("expected_prompt_tokens") is not None and l.get("prompt_tokens") is not None]
    out = {
        "n": len(rows),
        "errors": len(rows) - len(scored),
        "correct": sum(correct) / len(correct) if correct else None,
        "correct_ci95_low": lo, "correct_ci95_high": hi,
        "correct_answerable": _rate(ans, "correct")[0],
        "n_answerable": len(ans),
        "abstention_ooc": _rate(ooc, "correct")[0],
        "n_ooc": len(ooc),
        "abstained_answerable": (sum(r["metrics"]["outcome"] == ABSTAINED for r in ans) / len(ans)) if ans else None,
        "key_hit": _rate(ans, "key_hit")[0],
        "verdict_ok": _rate(ans, "verdict_ok")[0],
        "n_yes_no": _rate(ans, "verdict_ok")[1],
        "cited_not_delivered": _rate(scored, "cited_not_delivered")[0],
        "cited_gold": _rate(ans, "cited_gold")[0],
        "gold_delivered": _rate(rows, "gold_delivered")[0],
        "answer_delivered": _rate(rows, "answer_delivered")[0],
        "abstained_with_answer_in_context": _rate(ans, "abstained_with_answer_in_context")[0],
        "flags": sum(any(r["metrics"].get(f) for f in ("flag_says_cannot_but_answers", "flag_says_can_but_abstains",
                                                         "flag_answers_without_citation")) for r in scored),
        "mean_passage_tokens": _mean([r.get("passage_tokens") for r in rows]),
        "mean_expected_prompt_tokens": _mean([l.get("expected_prompt_tokens") for l in llm_rows]),
        "mean_server_prompt_tokens": _mean([l.get("prompt_tokens") for l in llm_rows]),
        "max_abs_delta_tokens": max((abs(d) for d in deltas), default=None),
        "mean_ms": _mean([l.get("ms") for l in llm_rows if not l.get("cached")]),
    }
    return out


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def two_by_two(rows: list[dict], retrieval_key: str = "gold_delivered") -> dict:
    """Por pregunta con respuesta: recuperó bien/mal × respondió bien/mal. Errores aparte."""
    cells = {"ret_ok_ans_ok": [], "ret_ok_ans_bad": [], "ret_bad_ans_ok": [], "ret_bad_ans_bad": [], "error": []}
    for r in rows:
        m = r["metrics"]
        if not m["answerable"]:
            continue
        if m["outcome"] == ERROR:
            cells["error"].append(r["item_id"])
            continue
        ret = "ret_ok" if m.get(retrieval_key) else "ret_bad"
        ans = "ans_ok" if m["correct"] else "ans_bad"
        cells[f"{ret}_{ans}"].append(r["item_id"])
    return {"retrieval_criterion": retrieval_key, "counts": {k: len(v) for k, v in cells.items()}, "items": cells}


def failure_kind(m: dict) -> str:
    """Etiqueta para abrir la caja (no reemplaza mirar la respuesta)."""
    if m["outcome"] == ERROR:
        return "error"
    if m["correct"]:
        return "ok"
    if not m["answerable"]:
        return "respondió una pregunta fuera del corpus"
    if m["outcome"] == ABSTAINED:
        return "se abstuvo con la respuesta en el contexto" if m.get("abstained_with_answer_in_context") else "se abstuvo"
    if m.get("verdict_ok") is False and m.get("key_hit"):
        return "veredicto sí/no equivocado"
    if m.get("gold_delivered") is False and m.get("n_citations") and not m.get("cited_not_delivered"):
        return "fiel al pasaje equivocado (candidato: verificar a mano)"
    if m.get("gold_delivered"):
        return "lo tenía, respondió otra cosa"
    return "respondió sin la clave"


def paired_comparison(rows_a: list[dict], rows_b: list[dict], metric: str = "correct",
                      seed: int = 1337, samples: int = 2000) -> dict:
    """B contra A sobre los mismos ítems: victorias/derrotas/empates, test de signos y bootstrap
    de la diferencia. Un ítem con error en cualquiera de las dos filas se excluye (y se cuenta)."""
    a = {r["item_id"]: r for r in rows_a}
    b = {r["item_id"]: r for r in rows_b}
    if a.keys() != b.keys():
        raise ValueError("La comparación pareada requiere los mismos ítems.")
    wins = losses = ties = excluded = 0
    diffs = []
    for k in sorted(a):
        p, q = a[k]["metrics"].get(metric), b[k]["metrics"].get(metric)
        if p is None or q is None:
            excluded += 1
            continue
        p, q = int(bool(p)), int(bool(q))
        wins += q > p
        losses += q < p
        ties += q == p
        diffs.append(q - p)
    n = wins + losses
    p_value = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2 ** n) if n else 1.0
    lo, hi = bootstrap_mean(diffs, seed, samples)
    return {"metric": metric, "wins": wins, "losses": losses, "ties": ties, "excluded_errors": excluded,
            "delta": (sum(diffs) / len(diffs)) if diffs else None, "delta_ci95": [lo, hi],
            "sign_test_p_two_sided": p_value}


def min_discordant_for_significance(alpha: float = 0.05) -> int:
    """Discordantes, todas en el mismo sentido, que hacen falta para p < alpha (p = 2 * 0.5^n)."""
    n = 1
    while 2 * 0.5 ** n >= alpha:
        n += 1
    return n


# --- lectura de la Etapa 3, con procedencia ---------------------------------------------------
def canonical_hash(value) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def read_jsonl(path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def find_stage3_run(art: Path, split: str, profile: str, override: Path | None = None) -> Path:
    """La carpeta results/stage3_<hash>/ terminada para este split y perfil.

    Con varias candidatas toma la más reciente y lo avisa; fijá STAGE3_RESULTS_DIR para elegir.
    """
    if override is not None:
        override = Path(override)
        if not (override / "retrieval.jsonl").is_file():
            raise FileNotFoundError(f"{override} no tiene retrieval.jsonl de la Etapa 3.")
        return override
    found = []
    for spec_path in sorted((Path(art) / "results").glob("stage3_*/run_spec.json")):
        d = spec_path.parent
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        report = d / "run_report.json"
        status = json.loads(report.read_text(encoding="utf-8")).get("status") if report.is_file() else None
        if spec.get("split") == split and spec.get("profile") == profile and status == "ok" \
                and (d / "retrieval.jsonl").is_file():
            found.append((json.loads(report.read_text(encoding="utf-8")).get("finished_at", ""), d))
    if not found:
        raise FileNotFoundError(
            f"No hay una corrida terminada de la Etapa 3 con split={split!r} y perfil={profile!r} en "
            f"{Path(art) / 'results'}. Corré 03_retrieval con esos valores (SMOKE_TEST y EVAL_SPLIT) primero.")
    found.sort()
    if len(found) > 1:
        print("AVISO: varias corridas de la Etapa 3 coinciden; uso la más reciente. Fijá STAGE3_RESULTS_DIR para elegir:")
        for when, d in found:
            print("   ", when, d)
    return found[-1][1]


def load_stage3_run(run_dir: Path, art: Path) -> dict:
    """run_spec + filas de retrieval + chunks del índice, verificando que sean del mismo índice."""
    run_dir = Path(run_dir)
    spec = json.loads((run_dir / "run_spec.json").read_text(encoding="utf-8"))
    rows = read_jsonl(run_dir / "retrieval.jsonl")
    index_dir = Path(art) / "index" / f"stage3_{spec['index_key'][:16]}"
    manifest_path = index_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Falta el índice de la Etapa 3 que usó esta corrida: {index_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if canonical_hash(manifest) != spec["index_key"]:
        raise ValueError("El manifiesto del índice no corresponde al index_key de la corrida de la Etapa 3.")
    chunks = read_jsonl(index_dir / "chunks.jsonl")
    if canonical_hash(chunks) != manifest["chunks_hash"]:
        raise ValueError("chunks.jsonl cambió después de construir el índice de la Etapa 3.")
    if {r["run_key"] for r in rows} != {canonical_hash(spec)}:
        raise ValueError("retrieval.jsonl tiene filas de otra corrida que la de run_spec.json.")
    if [r["item_id"] for r in rows] != spec["item_ids"]:
        raise ValueError("retrieval.jsonl no tiene exactamente los ítems de run_spec.json.")
    return {"dir": run_dir, "spec": spec, "rows": {r["item_id"]: r for r in rows},
            "index_dir": index_dir, "manifest": manifest, "chunks": {c["chunk_id"]: c for c in chunks}}


def oracle_passages(item: dict, docs: dict[str, dict], chunks_by_section: dict[str, list[dict]],
                    budget: int, count: Callable[[str], int]) -> tuple[list[dict], str]:
    """La sección gold entera, con el mismo formato de bloque que los hijos.

    Si una sección gold sola no entra en el presupuesto, se entregan sus hijos de la Etapa 3
    en orden de documento (el ensamblador corta). Devuelve (pasajes candidatos, modo).
    """
    out, mode = [], "section"
    for g in item.get("gold") or []:
        doc = docs[g["doc_id"]]
        secs = [s for s in doc["sections"] if s["section_id"] == g["section_id"]] if g.get("section_id") else []
        if not secs:
            raise ValueError(f"{item['item_id']}: gold sin sección utilizable {g}")
        s = secs[0]
        body = doc["text"][s["start"]:s["end"]]
        prefix = f"{doc['doc_id']} | {s['title']}\n"
        unit = {"chunk_id": s["section_id"], "doc_id": doc["doc_id"], "section_id": s["section_id"],
                "text": body, "index_text": prefix + body}
        if count(passage_block(unit)) <= budget:
            out.append(unit)
        else:
            mode = "children_fallback"
            out.extend(sorted(chunks_by_section.get(s["section_id"], []), key=lambda c: c["start"]))
    return out, mode
