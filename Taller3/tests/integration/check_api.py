import json
import subprocess
import sys
import tempfile
import os


def main():
    binary = sys.argv[1]
    p = subprocess.Popen([binary, "--api"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, encoding="utf-8")

    def call(**req):
        p.stdin.write(json.dumps(req) + "\n")
        p.stdin.flush()
        line = p.stdout.readline()
        assert line, "sin respuesta para %r" % req
        return json.loads(line)

    def ok(r):
        assert r["ok"] is True, r
        for f in ("result", "steps", "tree", "traversals", "state"):
            assert f in r, (f, r)
        assert set(r["traversals"]) == {"pre", "in", "post"}
        assert set(r["state"]) == {"dirty", "size"}
        return r

    r = ok(call(action="ping"))
    assert r["result"]["protocol"] == "1" and r["result"]["backend"] == "cpp"

    for k, lab in ((10, "diez"), (20, "veinte"), (30, "trein;ta")):
        r = ok(call(action="insert", key=k, label=lab))
    types = [s["t"] for s in r["steps"]]
    assert types[:4] == ["compare", "descend", "compare", "descend"], types
    assert "place" in types and "rotate" in types and "height" in types
    rot = [s for s in r["steps"] if s["t"] == "rotate"][0]
    assert rot["type"] == "RR" and rot["pivot"] == 10
    for s in r["steps"]:
        assert "tree" in s
    assert r["tree"]["k"] == 20 and r["tree"]["L"]["k"] == 10 and r["tree"]["R"]["k"] == 30
    assert set(r["tree"]) == {"k", "l", "a", "h", "bf", "L", "R"}
    assert r["traversals"] == {"pre": [20, 10, 30], "in": [10, 20, 30], "post": [10, 30, 20]}
    assert r["state"] == {"dirty": True, "size": 3}

    r = ok(call(action="search", key=20))
    assert r["result"]["found"] is True and r["result"]["label"] == "veinte"
    assert r["steps"][-1]["t"] == "found"
    r = ok(call(action="search", key=99))
    assert r["result"]["found"] is False and r["steps"][-1]["t"] == "notfound"

    r = ok(call(action="toggle", key=30))
    assert r["result"]["active"] is False
    assert r["steps"][-1] == {"t": "toggle", "key": 30, "active": False, "tree": r["tree"]}
    assert r["tree"]["R"]["a"] == 0
    r = ok(call(action="update", key=10, label="uno"))
    assert r["steps"][-1]["t"] == "update"

    path = os.path.join(tempfile.mkdtemp(), "sub", "a.txt")
    r = ok(call(action="save", key=None, path=path))
    assert r["state"]["dirty"] is False and r["steps"] == []
    ok(call(action="reset"))
    r = ok(call(action="state"))
    assert r["tree"] is None and r["state"]["size"] == 0
    r = ok(call(action="load", path=path))
    assert r["traversals"]["pre"] == [20, 10, 30] and r["tree"]["R"]["a"] == 0
    assert r["tree"]["R"]["l"] == "trein ta"

    r = call(action="insert", key=20, label="x")
    assert r["ok"] is False and r["error"] and "state" in r
    for bad in (dict(action="delete", key=77), dict(action="insert", key=2 ** 31),
                dict(action="insert", key=True), dict(action="nada"),
                dict(action="load", path=path + ".no")):
        r = call(**bad)
        assert r["ok"] is False and r["error"], (bad, r)
    r = ok(call(action="insert", key=-5, label="ñandú \"q\""))
    assert r["tree"]["L"]["L"]["l"] == "ñandú \"q\""
    r = ok(call(action="delete", key=20))
    assert any(s["t"] == "replace" for s in r["steps"]) and r["traversals"]["in"] == [-5, 10, 30]
    r = ok(call(action="traversals"))
    r = ok(call(action="undo"))  # deshace el borrado de 20
    assert r["traversals"]["in"] == [-5, 10, 20, 30] and r["state"]["dirty"] is True
    p.stdin.write("{no json\n")
    p.stdin.flush()
    assert json.loads(p.stdout.readline())["ok"] is False
    ok(call(action="shutdown"))
    p.wait(timeout=5)
    print("OK")


main()
