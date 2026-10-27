"""Genera notebooks/04_grounded_answers.ipynb a partir de notebooks/04_grounded_answers.py y grounded_stage4.py.

    python build_stage4_notebook.py           # escribe el notebook
    python build_stage4_notebook.py --check   # falla si el notebook no está al día

Igual que en la Etapa 3: el notebook lleva una copia del módulo en una celda (así se abre
solo en Colab, sin depender de haber subido el módulo al repo) y su hash queda en
IMPLEMENTATION_SHA256. El bootstrap es el de tools/py_to_notebook.py, con USE_DRIVE y
MODELS_ON_DRIVE activados, como en el notebook de la Etapa 3: la Etapa 4 lee los
artefactos de la Etapa 3 desde Drive.

Vive fuera de la raíz (como los notebooks 01-03 del grupo), así tools/py_to_notebook.py y
tools/check_repo.py no lo regeneran ni lo marcan como desactualizado.
No modifica ningún archivo existente del repo: solo escribe notebooks/04_grounded_answers.ipynb.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import py_to_notebook as p2n  # noqa: E402

SOURCE = ROOT / "notebooks" / "04_grounded_answers.py"
MODULE = ROOT / "grounded_stage4.py"
DESTINATION = ROOT / "notebooks" / "04_grounded_answers.ipynb"
MARKER = "@@GROUNDED_STAGE4_MODULE@@"


def render() -> str:
    cells = p2n.split_into_cells(SOURCE.read_text(encoding="utf-8"), SOURCE.name)
    module_text = MODULE.read_text(encoding="utf-8").rstrip("\n")
    digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    hits = [i for i, (kind, content) in enumerate(cells) if kind == "code" and MARKER in content]
    if len(hits) != 1:
        raise SystemExit(f"Esperaba una sola celda con {MARKER}, encontré {len(hits)}.")
    cells[hits[0]] = ("code", f"{module_text}\n\n\nIMPLEMENTATION_SHA256 = '{digest}'")
    bootstrap = p2n.bootstrap_cell()
    for flag in ("USE_DRIVE", "MODELS_ON_DRIVE"):
        if f"{flag} = False" not in bootstrap:
            raise SystemExit(f"El bootstrap cambió: no encontré '{flag} = False'.")
        bootstrap = bootstrap.replace(f"{flag} = False", f"{flag} = True", 1)
    cells = [("code", bootstrap)] + cells
    problems = p2n.check_code_cells(cells, SOURCE.name)
    if problems:
        raise SystemExit("\n".join(problems))
    return json.dumps(p2n.build_notebook(cells), ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        ok = DESTINATION.is_file() and DESTINATION.read_bytes() == text.encode("utf-8")
        print(f"{'OK' if ok else 'STALE'} {DESTINATION.name}")
        return 0 if ok else 1
    with open(DESTINATION, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"escrito {DESTINATION.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
