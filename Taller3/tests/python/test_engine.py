"""Pruebas del motor Python AVL (paa_engine). Ejecutar desde la raiz del proyecto:
    python3 -I -m unittest discover -s tests/python -t .
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "src", "python")
sys.path.insert(0, SRC)

import paa_engine  # noqa: E402
from paa_engine import AvlTree, Engine  # noqa: E402


def preorder(snap):
    if snap is None:
        return []
    return [snap["k"]] + preorder(snap["L"]) + preorder(snap["R"])


def all_nodes(snap):
    if snap is None:
        return []
    return [snap] + all_nodes(snap["L"]) + all_nodes(snap["R"])


def ins(e, k, label=""):
    return e.handle({"action": "insert", "key": k, "label": label})


def types(resp):
    return [s["t"] for s in resp["steps"]]


class RotationTests(unittest.TestCase):
    def check(self, keys, kind, pre):
        e = Engine()
        last = None
        for k in keys:
            last = ins(e, k)
            self.assertTrue(last["ok"])
        rot = [s for s in last["steps"] if s["t"] == "rotate"]
        self.assertEqual([r["type"] for r in rot], [kind])
        self.assertEqual(rot[0]["pivot"], keys[0])
        self.assertEqual(preorder(last["tree"]), pre)
        self.assertEqual(last["traversals"]["pre"], pre)

    def test_rr(self):
        self.check([10, 20, 30], "RR", [20, 10, 30])

    def test_ll(self):
        self.check([30, 20, 10], "LL", [20, 10, 30])

    def test_rl(self):
        self.check([10, 30, 20], "RL", [20, 10, 30])

    def test_lr(self):
        self.check([30, 10, 20], "LR", [20, 10, 30])


class StepContractTests(unittest.TestCase):
    def test_insert_steps_and_snapshots(self):
        e = Engine()
        ins(e, 20)
        r = ins(e, 10)
        self.assertEqual(types(r), ["compare", "descend", "place", "height"])
        self.assertEqual(r["steps"][0]["key"], 10)
        self.assertEqual(r["steps"][0]["with"], 20)
        self.assertEqual(r["steps"][1]["dir"], "L")
        self.assertEqual(r["steps"][2]["key"], 10)
        self.assertEqual(r["steps"][3], {**r["steps"][3], "key": 20, "h": 2, "bf": 1})
        for s in r["steps"]:
            self.assertIn("tree", s)
        self.assertEqual(r["steps"][-1]["tree"], r["tree"])
        snap = r["tree"]
        self.assertEqual(set(snap), {"k", "l", "a", "h", "bf", "L", "R"})
        self.assertEqual(snap["a"], 1)

    def test_height_steps_bottom_up_then_rotate(self):
        e = Engine()
        ins(e, 10)
        ins(e, 20)
        r = ins(e, 30)
        t = types(r)
        self.assertEqual(t[-3:], ["height", "height", "rotate"])
        hs = [s for s in r["steps"] if s["t"] == "height"]
        self.assertEqual([h["key"] for h in hs], [20, 10])
        self.assertEqual(hs[-1]["bf"], -2)

    def test_delete_two_children_uses_successor(self):
        e = Engine()
        for k in (20, 10, 30, 25, 40):
            ins(e, k)
        r = e.handle({"action": "delete", "key": 20})
        self.assertTrue(r["ok"])
        t = types(r)
        self.assertIn("replace", t)
        rep = [s for s in r["steps"] if s["t"] == "replace"][0]
        self.assertEqual((rep["key"], rep["with"]), (20, 25))
        self.assertEqual(r["traversals"]["in"], [10, 25, 30, 40])
        self.assertEqual(r["steps"][-1]["tree"], r["tree"])


class DeleteTests(unittest.TestCase):
    def build(self, keys):
        e = Engine()
        for k in keys:
            ins(e, k, "n%d" % k)
        return e

    def test_leaf(self):
        e = self.build([20, 10, 30])
        r = e.handle({"action": "delete", "key": 10})
        self.assertTrue(r["ok"])
        self.assertEqual(r["traversals"]["in"], [20, 30])
        self.assertIn("remove", types(r))
        self.assertEqual(r["state"]["size"], 2)

    def test_one_child(self):
        e = self.build([20, 10, 30, 5])
        r = e.handle({"action": "delete", "key": 10})
        self.assertEqual(r["traversals"]["pre"], [20, 5, 30])

    def test_two_children(self):
        e = self.build([20, 10, 30, 25, 40])
        r = e.handle({"action": "delete", "key": 30})
        self.assertEqual(r["traversals"]["in"], [10, 20, 25, 40])
        self.assertEqual(
            [n["l"] for n in all_nodes(r["tree"]) if n["k"] == 25], ["n25"])

    def test_delete_rebalances(self):
        e = self.build([20, 10, 30, 5])
        e.handle({"action": "delete", "key": 30})
        r = e.handle({"action": "state"})
        for n in all_nodes(r["tree"]):
            self.assertLessEqual(abs(n["bf"]), 1)

    def test_delete_triggers_rotation(self):
        e = self.build([20, 10, 30, 5])
        r = e.handle({"action": "delete", "key": 30})
        self.assertIn("rotate", types(r))
        self.assertEqual(r["tree"]["k"], 10)

    def test_missing_key(self):
        e = self.build([1])
        r = e.handle({"action": "delete", "key": 99})
        self.assertFalse(r["ok"])
        self.assertIsInstance(r["error"], str)
        self.assertEqual(r["state"]["size"], 1)

    def test_empty_tree(self):
        e = Engine()
        r = e.handle({"action": "delete", "key": 1})
        self.assertFalse(r["ok"])
        s = e.handle({"action": "search", "key": 1})
        self.assertTrue(s["ok"])
        self.assertFalse(s["result"]["found"])
        self.assertEqual(types(s), ["notfound"])
        self.assertIsNone(s["tree"])


class ErrorTests(unittest.TestCase):
    def test_duplicate(self):
        e = Engine()
        ins(e, 5, "a")
        r = ins(e, 5, "b")
        self.assertFalse(r["ok"])
        self.assertEqual(e.handle({"action": "state"})["state"]["size"], 1)
        self.assertEqual(r["state"]["size"], 1)

    def test_bad_requests(self):
        e = Engine()
        for req in ({}, {"action": "nope"}, {"action": "insert", "key": "x"},
                    {"action": "insert", "key": True},
                    {"action": "insert", "key": 2 ** 31},
                    {"action": "toggle", "key": 1},
                    {"action": "update", "key": 1, "label": "x"}):
            r = e.handle(req)
            self.assertFalse(r["ok"], req)
            self.assertIn("error", r)

    def test_int32_extremes(self):
        e = Engine()
        for k in (-2 ** 31, -1, 0, 2 ** 31 - 1):
            self.assertTrue(ins(e, k)["ok"])
        self.assertEqual(e.handle({"action": "traversals"})["traversals"]["in"],
                         [-2 ** 31, -1, 0, 2 ** 31 - 1])

    def test_ping(self):
        r = Engine().handle({"action": "ping"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["result"]["protocol"], "1")
        self.assertEqual(r["result"]["backend"], "python")


class OtherActionTests(unittest.TestCase):
    def test_search_toggle_update_reset(self):
        e = Engine()
        ins(e, 1, "uno")
        s = e.handle({"action": "search", "key": 1})
        self.assertTrue(s["result"]["found"])
        self.assertTrue(s["result"]["active"])
        self.assertEqual(types(s)[-1], "found")
        t = e.handle({"action": "toggle", "key": 1})
        self.assertEqual(t["steps"][-1]["t"], "toggle")
        self.assertFalse(t["steps"][-1]["active"])
        self.assertEqual(t["tree"]["a"], 0)
        s = e.handle({"action": "search", "key": 1})
        self.assertFalse(s["result"]["active"])
        u = e.handle({"action": "update", "key": 1, "label": "nuevo"})
        self.assertEqual(u["tree"]["l"], "nuevo")
        self.assertEqual(u["steps"][-1]["t"], "update")
        r = e.handle({"action": "reset"})
        self.assertIsNone(r["tree"])
        self.assertEqual(r["state"], {"dirty": False, "size": 0})

    def test_dirty_flag(self):
        e = Engine()
        self.assertFalse(e.handle({"action": "state"})["state"]["dirty"])
        self.assertTrue(ins(e, 1)["state"]["dirty"])


class LargeTests(unittest.TestCase):
    def test_ascending_1000(self):
        t = AvlTree(record=False)
        n = 1000
        for k in range(1, n + 1):
            t.insert(k, "")
        snap = t.snapshot()
        self.assertLessEqual(snap["h"], 1.44 * math.log2(n))
        nodes = all_nodes(snap)
        self.assertEqual(len(nodes), n)
        self.assertTrue(all(abs(x["bf"]) <= 1 for x in nodes))
        self.assertEqual(t.traversals()["in"], list(range(1, n + 1)))

    def test_delete_half_keeps_balance(self):
        t = AvlTree(record=False)
        for k in range(1, 501):
            t.insert(k, "")
        for k in range(1, 501, 2):
            t.delete(k)
        nodes = all_nodes(t.snapshot())
        self.assertEqual(len(nodes), 250)
        self.assertTrue(all(abs(x["bf"]) <= 1 for x in nodes))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "arbol.txt")

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        e = Engine()
        for k in (50, 30, 70, 20, 40, 60, 80, 10):
            ins(e, k, "n%d" % k)
        e.handle({"action": "toggle", "key": 40})
        r = e.handle({"action": "save", "path": self.path})
        self.assertTrue(r["ok"])
        self.assertFalse(r["state"]["dirty"])
        before = e.handle({"action": "state"})["tree"]
        e2 = Engine()
        r2 = e2.handle({"action": "load", "path": self.path})
        self.assertTrue(r2["ok"])
        self.assertEqual(r2["tree"], before)
        self.assertEqual(r2["traversals"]["pre"], preorder(before))
        self.assertFalse(r2["state"]["dirty"])
        with open(self.path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "%d;n%d;1" % (before["k"], before["k"]))
        self.assertIn("40;n40;0", lines)

    def test_label_sanitized(self):
        e = Engine()
        ins(e, 1, "a;b\nc\r\nd")
        e.handle({"action": "save", "path": self.path})
        e2 = Engine()
        self.assertTrue(e2.handle({"action": "load", "path": self.path})["ok"])
        self.assertEqual(e2.handle({"action": "state"})["tree"]["l"], "a b c  d")
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(len(f.read().splitlines()), 1)

    def test_unicode_label(self):
        e = Engine()
        ins(e, 1, "árbol ñ")
        e.handle({"action": "save", "path": self.path})
        e2 = Engine()
        e2.handle({"action": "load", "path": self.path})
        self.assertEqual(e2.handle({"action": "state"})["tree"]["l"], "árbol ñ")

    def test_corrupt_leaves_tree_untouched(self):
        e = Engine()
        ins(e, 5, "keep")
        before = e.handle({"action": "state"})["tree"]
        bad = ["1;a;1\nxyz\n", "1;a;1\n2;b;7\n", "1;a;1\nx;b;1\n",
               "1;a;1\n1;b;1\n", "", "\n"]
        for content in bad:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(content)
            r = e.handle({"action": "load", "path": self.path})
            self.assertFalse(r["ok"], content)
            self.assertIsInstance(r["error"], str)
            self.assertEqual(e.handle({"action": "state"})["tree"], before)

    def test_missing_file(self):
        e = Engine()
        r = e.handle({"action": "load", "path": os.path.join(self.tmp.name, "no.txt")})
        self.assertFalse(r["ok"])

    def test_default_path_from_constructor(self):
        e = Engine(data_path=self.path)
        ins(e, 3, "x")
        self.assertTrue(e.handle({"action": "save"})["ok"])
        self.assertTrue(os.path.exists(self.path))
        self.assertTrue(e.handle({"action": "load"})["ok"])

    def test_no_path_error(self):
        self.assertFalse(Engine().handle({"action": "save"})["ok"])


class CliTests(unittest.TestCase):
    def test_api_mode(self):
        reqs = [{"action": "ping"},
                {"action": "insert", "key": 1, "label": "a"},
                {"action": "insert", "key": 1, "label": "a"},
                {"action": "shutdown"},
                {"action": "ping"}]
        inp = "\n".join(json.dumps(r) for r in reqs[:3]) + "\nnot json\n" \
            + json.dumps(reqs[3]) + "\n" + json.dumps(reqs[4]) + "\n"
        p = subprocess.run(
            [sys.executable, "-I", os.path.join(SRC, "paa_engine.py"), "--api"],
            input=inp.encode("utf-8"), capture_output=True, timeout=30)
        out = [json.loads(x) for x in p.stdout.decode("utf-8").splitlines()]
        self.assertEqual(len(out), 5)  # tras shutdown no se atiende nada mas
        self.assertEqual(out[0]["result"]["protocol"], "1")
        self.assertTrue(out[1]["ok"])
        self.assertFalse(out[2]["ok"])
        self.assertFalse(out[3]["ok"])
        self.assertTrue(out[4]["ok"])
        self.assertEqual(p.returncode, 0)


class TestUndo(unittest.TestCase):
    def test_undo_restores_each_operation(self):
        e = Engine()
        shapes = [e.handle({"action": "traversals"})["tree"]]
        ops = [{"action": "insert", "key": k, "label": "n%d" % k} for k in (10, 20, 30, 25)]
        ops += [{"action": "toggle", "key": 20}, {"action": "update", "key": 10, "label": "x"},
                {"action": "delete", "key": 20}]
        for op in ops:
            self.assertTrue(e.handle(op)["ok"])
            shapes.append(e.handle({"action": "traversals"})["tree"])
        for expected in reversed(shapes[:-1]):
            r = e.handle({"action": "undo"})
            self.assertTrue(r["ok"])
            self.assertEqual(r["tree"], expected)
            self.assertTrue(r["state"]["dirty"])

    def test_undo_without_history_and_failed_ops(self):
        e = Engine()
        self.assertFalse(e.handle({"action": "undo"})["ok"])
        e.handle({"action": "insert", "key": 1})
        self.assertFalse(e.handle({"action": "insert", "key": 1})["ok"])  # duplicada: no cuenta
        self.assertFalse(e.handle({"action": "delete", "key": 9})["ok"])
        self.assertTrue(e.handle({"action": "undo"})["ok"])
        self.assertIsNone(e.handle({"action": "traversals"})["tree"])
        self.assertFalse(e.handle({"action": "undo"})["ok"])


if __name__ == "__main__":
    unittest.main()
