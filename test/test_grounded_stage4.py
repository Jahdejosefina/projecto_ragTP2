"""Pruebas de la Etapa 4 que no necesitan Ollama, GPU ni descargas.

    python -m unittest tests.test_grounded_stage4 -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from grounded_stage4 import (  # noqa: E402
    ABSTAINED, ANSWERED, ERROR, GroundedAnswer, Stage4Config, assemble, build_messages,
    check_schema_order, contains_key, failure_kind, fit_prompt, min_discordant_for_significance,
    normalize_citation, oracle_passages, paired_comparison, passage_block, render_passages,
    score_answer, summarize_arm, two_by_two,
)


def count(text):            # 1 token = 1 palabra: suficiente para probar la lógica
    return len(text.split())


def count_messages(messages):
    return sum(count(m["content"]) + 4 for m in messages) + 3


def chunk(cid, sec, text, doc="LEY-1"):
    return {"chunk_id": cid, "doc_id": doc, "section_id": sec, "text": text,
            "index_text": f"{doc} | t\n{text}", "start": 0}


ITEM = {"item_id": "q1", "question": "¿Cuánto dura la garantía?", "category": "topical", "answerable": True,
        "gold": [{"doc_id": "LEY-1", "section_id": "LEY-1#ART-11"}], "answer_key": ["tres meses", "3 meses"],
        "expected_verdict": None}
YESNO = {**ITEM, "item_id": "q2", "answer_key": ["gratuita"], "expected_verdict": "no"}
OOC = {"item_id": "q3", "question": "¿Mi expediente?", "category": "out_of_corpus", "answerable": False,
       "gold": [], "answer_key": None, "expected_verdict": None}
GOLD_CHUNK = chunk("c1", "LEY-1#ART-11", "la garantía será de tres meses")
OTHER_CHUNK = chunk("c2", "LEY-1#ART-12", "otra cosa distinta")


def ans(answer="Tres meses.", can=True, cites=("LEY-1#ART-11",), verdict="no_aplica"):
    return GroundedAnswer(analysis="a", answer=answer, can_answer=can, citations=list(cites), verdict=verdict)


class TestSchema(unittest.TestCase):
    def test_reasoning_first_in_declaration_and_alphabetical_order(self):
        props = check_schema_order()
        self.assertEqual(props[0], "analysis")
        self.assertEqual(sorted(props)[0], "analysis")

    def test_all_fields_required(self):
        schema = GroundedAnswer.model_json_schema()
        self.assertEqual(set(schema["required"]), set(schema["properties"]))


class TestAssembler(unittest.TestCase):
    def test_skips_and_continues(self):
        big = chunk("big", "S#1", "x " * 500)
        small = chunk("small", "S#2", "dato breve")
        budget = count(passage_block(small)) + 2
        kept, skipped, used = assemble([big, small], budget, count)
        self.assertEqual([p["chunk_id"] for p in kept], ["small"])
        self.assertEqual([p["chunk_id"] for p in skipped], ["big"])
        self.assertLessEqual(used, budget)

    def test_never_exceeds_budget(self):
        ps = [chunk(f"c{i}", f"S#{i}", "palabra " * (i * 7 % 40 + 1)) for i in range(50)]
        for budget in (10, 50, 137, 400):
            kept, _, used = assemble(ps, budget, count)
            self.assertLessEqual(count(render_passages(kept)) if kept else 0, budget)
            self.assertEqual(used, count(render_passages(kept)) if kept else 0)

    def test_fit_prompt_checks_whole_prompt(self):
        cfg = Stage4Config(num_ctx=300, num_predict=100, safety_margin=0, passage_budget=150)
        ps = [chunk(f"c{i}", f"S#{i}", "palabra " * 30) for i in range(10)]
        fp = fit_prompt("sistema " * 40, "pregunta", ps, cfg, count, count_messages)
        self.assertTrue(fp.fits)
        self.assertLessEqual(fp.expected_prompt_tokens, cfg.prompt_limit)
        self.assertLessEqual(fp.passage_tokens, cfg.passage_budget)

    def test_closed_book_has_no_passage_block(self):
        msgs = build_messages("s", "¿q?", None)
        self.assertNotIn("PASAJES", msgs[-1]["content"])
        self.assertTrue(msgs[-1]["content"].endswith("¿q?"))

    def test_question_is_last_and_markers_present(self):
        msgs = build_messages("s", "¿q?", [GOLD_CHUNK])
        content = msgs[-1]["content"]
        self.assertIn("[LEY-1 · LEY-1#ART-11]", content)
        self.assertTrue(content.endswith("PREGUNTA: ¿q?"))

    def test_config_rejects_bad_budgets(self):
        with self.assertRaises(ValueError):
            Stage4Config(num_ctx=1000, num_predict=1000)
        with self.assertRaises(ValueError):
            Stage4Config(passage_budget=8000)


class TestScoring(unittest.TestCase):
    def test_key_normalization(self):
        self.assertTrue(contains_key("Son 3 meses.", ["tres meses", "3 meses"]))
        self.assertTrue(contains_key("La Ley 24.240 dice", ["24240"]))
        self.assertTrue(contains_key("doce (12) años", ["doce años"]))
        self.assertTrue(contains_key("INFORMACIÓN GRATUITA", ["informacion gratuita"]))
        self.assertTrue(contains_key("una tasa de 1,5 por ciento", ["1.5"]))
        self.assertFalse(contains_key("trescientos días", ["tres"]))   # palabra entera, no prefijo

    def test_citation_normalization(self):
        for raw in ("LEY-1#ART-11", "[LEY-1 · LEY-1#ART-11]", " LEY-1 · LEY-1#ART-11 ", "[LEY-1#ART-11]"):
            self.assertEqual(normalize_citation(raw), "LEY-1#ART-11")

    def test_correct_answer(self):
        m = score_answer(ITEM, ans(), None, [GOLD_CHUNK, OTHER_CHUNK])
        self.assertEqual(m["outcome"], ANSWERED)
        self.assertTrue(m["correct"] and m["key_hit"] and m["cited_gold"] and m["gold_delivered"])
        self.assertFalse(m["cited_not_delivered"])

    def test_abstention_is_the_boolean_not_the_text(self):
        # Texto de abstención en el análisis, pero can_answer=True y la clave en la respuesta: respondió.
        a = GroundedAnswer(analysis="No lo sé al principio, pero", answer="tres meses", can_answer=True,
                           citations=["LEY-1#ART-11"], verdict="no_aplica")
        self.assertEqual(score_answer(ITEM, a, None, [GOLD_CHUNK])["outcome"], ANSWERED)
        # Respuesta parafraseada sin "No lo sé" pero can_answer=False: se abstuvo.
        m = score_answer(ITEM, ans(answer="El contexto no alcanza.", can=False, cites=()), None, [GOLD_CHUNK])
        self.assertEqual(m["outcome"], ABSTAINED)
        self.assertTrue(m["abstained_with_answer_in_context"])

    def test_error_is_its_own_category(self):
        m = score_answer(ITEM, None, "PARSE_FAILED: x", [GOLD_CHUNK])
        self.assertEqual(m["outcome"], ERROR)
        self.assertIsNone(m["correct"])
        self.assertEqual(failure_kind(m), "error")

    def test_citation_not_delivered(self):
        m = score_answer(ITEM, ans(cites=("LEY-9#ART-1",)), None, [GOLD_CHUNK])
        self.assertTrue(m["cited_not_delivered"])
        self.assertEqual(m["invalid_citations"], ["LEY-9#ART-1"])

    def test_yes_no_verdict_scored_apart(self):
        good = score_answer(YESNO, ans(answer="No, es gratuita.", verdict="no", cites=("LEY-1#ART-11",)), None, [GOLD_CHUNK])
        bad = score_answer(YESNO, ans(answer="Sí, es gratuita.", verdict="si", cites=("LEY-1#ART-11",)), None, [GOLD_CHUNK])
        self.assertTrue(good["correct"])
        self.assertTrue(bad["key_hit"])
        self.assertFalse(bad["correct"])
        self.assertEqual(failure_kind(bad), "veredicto sí/no equivocado")

    def test_out_of_corpus(self):
        self.assertTrue(score_answer(OOC, ans(answer="No hay información suficiente.", can=False, cites=()), None, [])["correct"])
        self.assertFalse(score_answer(OOC, ans(answer="El 3 de marzo.", cites=()), None, [])["correct"])

    def test_faithful_to_wrong_passage_candidate(self):
        m = score_answer(ITEM, ans(answer="otra cosa", cites=("LEY-1#ART-12",)), None, [OTHER_CHUNK])
        self.assertFalse(m["gold_delivered"])
        self.assertTrue(failure_kind(m).startswith("fiel al pasaje equivocado"))

    def test_consistency_flags(self):
        m = score_answer(ITEM, ans(answer="Tres meses.", can=False, cites=()), None, [GOLD_CHUNK])
        self.assertTrue(m["flag_says_cannot_but_answers"])
        m = score_answer(ITEM, ans(answer="No hay información suficiente en los pasajes.", can=True, cites=()), None, [GOLD_CHUNK])
        self.assertTrue(m["flag_says_can_but_abstains"])

    def test_closed_book_has_no_delivery_metrics(self):
        m = score_answer(ITEM, ans(cites=()), None, [], closed_book=True)
        self.assertIsNone(m["gold_delivered"])
        self.assertIsNone(m["abstained_with_answer_in_context"])


class TestTables(unittest.TestCase):
    def rows(self, outcomes):
        out = []
        for i, (gold_delivered, correct) in enumerate(outcomes):
            out.append({"item_id": f"q{i}", "metrics": {"answerable": True, "outcome": ANSWERED,
                                                         "gold_delivered": gold_delivered, "correct": correct}})
        return out

    def test_two_by_two(self):
        tt = two_by_two(self.rows([(True, True), (True, False), (False, True), (False, False), (False, False)]))
        self.assertEqual(tt["counts"], {"ret_ok_ans_ok": 1, "ret_ok_ans_bad": 1, "ret_bad_ans_ok": 1,
                                        "ret_bad_ans_bad": 2, "error": 0})

    def test_sign_test(self):
        a = self.rows([(True, False)] * 6)
        b = self.rows([(True, True)] * 6)
        r = paired_comparison(a, b)
        self.assertEqual((r["wins"], r["losses"]), (6, 0))
        self.assertAlmostEqual(r["sign_test_p_two_sided"], 2 * 0.5 ** 6)
        self.assertEqual(min_discordant_for_significance(), 6)

    def test_paired_excludes_errors(self):
        a = self.rows([(True, True), (True, False)])
        b = self.rows([(True, True), (True, True)])
        b[1]["metrics"]["correct"] = None
        self.assertEqual(paired_comparison(a, b)["excluded_errors"], 1)

    def test_summary_counts_errors_apart(self):
        rows = self.rows([(True, True), (True, False)])
        rows.append({"item_id": "e", "metrics": {"answerable": True, "outcome": ERROR, "correct": None}})
        s = summarize_arm(rows, Stage4Config())
        self.assertEqual(s["errors"], 1)
        self.assertEqual(s["correct"], 0.5)


class TestOracle(unittest.TestCase):
    def test_whole_section_or_children(self):
        text = "Encabezado.\nARTICULO 11. la garantía será de tres meses " + "relleno " * 200
        doc = {"doc_id": "LEY-1", "text": text, "sections": [
            {"section_id": "LEY-1#ART-11", "title": "Artículo 11", "start": 12, "end": len(text)}]}
        children = {"LEY-1#ART-11": [{**chunk("k2", "LEY-1#ART-11", "relleno"), "start": 50},
                                     {**chunk("k1", "LEY-1#ART-11", "tres meses"), "start": 12}]}
        whole, mode = oracle_passages(ITEM, {"LEY-1": doc}, children, 10_000, count)
        self.assertEqual(mode, "section")
        self.assertEqual(len(whole), 1)
        parts, mode = oracle_passages(ITEM, {"LEY-1": doc}, children, 50, count)
        self.assertEqual(mode, "children_fallback")
        self.assertEqual([p["chunk_id"] for p in parts], ["k1", "k2"])


if __name__ == "__main__":
    unittest.main()
