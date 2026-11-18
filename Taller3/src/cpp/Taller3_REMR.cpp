// PAA - Programa de Aprendizaje de Árboles AVL (Taller 3, REMR). Motor C++17.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

using std::string;
using std::vector;

struct Node {
    int key = 0;
    string label;
    bool active = true;
    int h = 1;
    std::unique_ptr<Node> l, r;
};

struct Step {
    string t;
    string json;
};

struct Traversals {
    vector<int> pre, in, post;
};

static string jstr(const string& s) {
    string o = "\"";
    for (unsigned char c : s) {
        switch (c) {
            case '"': o += "\\\""; break;
            case '\\': o += "\\\\"; break;
            case '\n': o += "\\n"; break;
            case '\r': o += "\\r"; break;
            case '\t': o += "\\t"; break;
            default:
                if (c < 0x20) {
                    char b[8];
                    std::snprintf(b, sizeof b, "\\u%04x", c);
                    o += b;
                } else {
                    o += static_cast<char>(c);
                }
        }
    }
    return o + "\"";
}

static bool parseInt32(const string& s, int& out) {
    if (s.empty() || s.size() > 11) return false;
    size_t i = (s[0] == '-') ? 1 : 0;
    if (i == s.size()) return false;
    for (size_t j = i; j < s.size(); ++j)
        if (s[j] < '0' || s[j] > '9') return false;
    long long v = std::stoll(s);
    if (v < INT32_MIN || v > INT32_MAX) return false;
    out = static_cast<int>(v);
    return true;
}

class AvlTree {
public:
    bool record = false;
    vector<Step> steps;
    vector<std::pair<string, int>> rotations;
    std::unique_ptr<Node> root;

    bool insert(int key, const string& label, string& err) {
        begin();
        vector<Slot> path;
        Slot cur = &root;
        while (*cur) {
            Node* n = cur->get();
            emit("compare", fk(key) + ",\"with\":" + std::to_string(n->key));
            if (key == n->key) return fail(err, "La clave " + std::to_string(key) + " ya existe");
            bool left = key < n->key;
            emit("descend", string(",\"dir\":\"") + (left ? "L" : "R") + "\"");
            path.push_back(cur);
            cur = left ? &n->l : &n->r;
        }
        *cur = std::make_unique<Node>();
        (*cur)->key = key;
        (*cur)->label = label;
        emit("place", fk(key));
        rebalance(path);
        return true;
    }

    bool erase(int key, string& err) {
        begin();
        vector<Slot> path;
        Slot cur = &root;
        while (true) {
            if (!*cur) return fail(err, "La clave " + std::to_string(key) + " no existe");
            Node* n = cur->get();
            emit("compare", fk(key) + ",\"with\":" + std::to_string(n->key));
            if (key == n->key) break;
            bool left = key < n->key;
            emit("descend", string(",\"dir\":\"") + (left ? "L" : "R") + "\"");
            path.push_back(cur);
            cur = left ? &n->l : &n->r;
        }
        Node* n = cur->get();
        if (!n->l || !n->r) {
            std::unique_ptr<Node> child = n->l ? std::move(n->l) : std::move(n->r);
            *cur = std::move(child);
            emit("remove", fk(key));
        } else {
            path.push_back(cur);
            Slot s = &n->r;
            emit("descend", ",\"dir\":\"R\"");
            while ((*s)->l) {
                path.push_back(s);
                emit("descend", ",\"dir\":\"L\"");
                s = &(*s)->l;
            }
            Node* succ = s->get();
            int sk = succ->key;
            n->key = sk;
            n->label = succ->label;
            n->active = succ->active;
            emit("replace", fk(key) + ",\"with\":" + std::to_string(sk));
            std::unique_ptr<Node> child = std::move(succ->r);
            *s = std::move(child);
            emit("remove", fk(sk));
        }
        rebalance(path);
        return true;
    }

    const Node* peek(int key) const {
        const Node* n = root.get();
        while (n && n->key != key) n = key < n->key ? n->l.get() : n->r.get();
        return n;
    }

    const Node* search(int key) {
        begin();
        const Node* n = walk(key);
        emit(n ? "found" : "notfound", fk(key));
        return n;
    }

    bool toggle(int key, string& err) {
        begin();
        Node* n = walk(key);
        if (!n) return fail(err, "La clave " + std::to_string(key) + " no existe");
        n->active = !n->active;
        emit("toggle", fk(key) + ",\"active\":" + (n->active ? "true" : "false"));
        return true;
    }

    bool updateLabel(int key, const string& label, string& err) {
        begin();
        Node* n = walk(key);
        if (!n) return fail(err, "La clave " + std::to_string(key) + " no existe");
        n->label = label;
        emit("update", fk(key));
        return true;
    }

    void clear() {
        root.reset();
        steps.clear();
        rotations.clear();
    }

    size_t size() const { return count(root.get()); }

    Traversals traversals() const {
        Traversals t;
        trav(root.get(), t);
        return t;
    }

    string snapshot() const {
        string o;
        snap(root.get(), o);
        return o;
    }

    bool save(const string& path, string& err) const {
        std::filesystem::path p(path);
        std::error_code ec;
        if (p.has_parent_path()) std::filesystem::create_directories(p.parent_path(), ec);
        // Se escribe en un archivo temporal y se reemplaza el destino al final: un fallo no destruye el archivo anterior.
        const string tmp = path + ".tmp";
        {
            std::ofstream f(tmp, std::ios::binary);
            if (!f) {
                err = "No se pudo escribir el archivo: " + path;
                return false;
            }
            writePre(root.get(), f);
            f.flush();
            if (!f) {
                err = "Error al escribir el archivo: " + path;
                f.close();
                std::filesystem::remove(tmp, ec);
                return false;
            }
        }
        std::filesystem::rename(tmp, path, ec);
        if (ec) {
            std::filesystem::remove(tmp, ec);
            err = "No se pudo reemplazar el archivo: " + path;
            return false;
        }
        return true;
    }

    string serialize() const {
        std::ostringstream o;
        writePre(root.get(), o);
        return o.str();
    }

    bool load(const string& path, string& err) {
        std::ifstream f(path, std::ios::binary);
        if (!f) {
            err = "No se pudo abrir el archivo: " + path;
            return false;
        }
        return loadStream(f, err, "El archivo esta vacio: " + path);
    }

    // emptyMsg vacio = se acepta un arbol vacio (deshacer)
    bool loadStream(std::istream& f, string& err, const string& emptyMsg) {
        struct Ent { int key; string label; bool act; };
        vector<Ent> ents;
        string line;
        int lineNo = 0;
        while (std::getline(f, line)) {
            ++lineNo;
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) continue;
            size_t p1 = line.find(';'), p2 = line.rfind(';');
            int key;
            if (p1 == string::npos || p1 == p2 || !parseInt32(line.substr(0, p1), key) ||
                (line.substr(p2 + 1) != "0" && line.substr(p2 + 1) != "1")) {
                err = "Archivo corrupto en la linea " + std::to_string(lineNo);
                return false;
            }
            ents.push_back({key, line.substr(p1 + 1, p2 - p1 - 1), line.substr(p2 + 1) == "1"});
        }
        if (ents.empty() && !emptyMsg.empty()) {
            err = emptyMsg;
            return false;
        }
        if (ents.size() > 20000) {  // misma regla que el motor Python: evita arboles temporales muy profundos
            err = "El archivo tiene demasiados nodos (maximo 20000)";
            return false;
        }
        AvlTree tmp;
        for (const auto& en : ents) {
            Slot c = &tmp.root;
            while (*c) {
                if (en.key == (*c)->key) {
                    err = "Archivo corrupto: clave duplicada " + std::to_string(en.key);
                    return false;
                }
                c = en.key < (*c)->key ? &(*c)->l : &(*c)->r;
            }
            *c = std::make_unique<Node>();
            (*c)->key = en.key;
            (*c)->label = en.label;
            (*c)->active = en.act;
        }
        bool ok = true;
        fixHeights(tmp.root.get(), ok);
        if (!ok) {
            AvlTree bal;
            string e;
            for (const auto& en : ents) {
                bal.insert(en.key, en.label, e);
                bal.setActive(en.key, en.act);
            }
            tmp.root = std::move(bal.root);
        }
        root = std::move(tmp.root);
        steps.clear();
        rotations.clear();
        return true;
    }

private:
    using Slot = std::unique_ptr<Node>*;

    static int hOf(const Node* n) { return n ? n->h : 0; }
    static int bfOf(const Node* n) { return hOf(n->l.get()) - hOf(n->r.get()); }
    static void upd(Node* n) { n->h = 1 + std::max(hOf(n->l.get()), hOf(n->r.get())); }
    static string fk(int k) { return ",\"key\":" + std::to_string(k); }

    void begin() {
        steps.clear();
        rotations.clear();
    }
    bool fail(string& err, const string& m) {
        steps.clear();
        rotations.clear();
        err = m;
        return false;
    }
    void emit(const string& t, const string& fields) {
        if (!record) return;
        steps.push_back({t, "{\"t\":\"" + t + "\"" + fields + ",\"tree\":" + snapshot() + "}"});
    }
    void setActive(int key, bool a) {
        Node* n = root.get();
        while (n && n->key != key) n = key < n->key ? n->l.get() : n->r.get();
        if (n) n->active = a;
    }
    Node* walk(int key) {
        Node* n = root.get();
        while (n) {
            emit("compare", fk(key) + ",\"with\":" + std::to_string(n->key));
            if (key == n->key) return n;
            bool left = key < n->key;
            emit("descend", string(",\"dir\":\"") + (left ? "L" : "R") + "\"");
            n = left ? n->l.get() : n->r.get();
        }
        return nullptr;
    }

    static void rotR(Slot s) {
        std::unique_ptr<Node> z = std::move(*s);
        std::unique_ptr<Node> y = std::move(z->l);
        z->l = std::move(y->r);
        upd(z.get());
        y->r = std::move(z);
        upd(y.get());
        *s = std::move(y);
    }
    static void rotL(Slot s) {
        std::unique_ptr<Node> z = std::move(*s);
        std::unique_ptr<Node> y = std::move(z->r);
        z->r = std::move(y->l);
        upd(z.get());
        y->l = std::move(z);
        upd(y.get());
        *s = std::move(y);
    }

    void rebalance(const vector<Slot>& path) {
        for (size_t i = path.size(); i-- > 0;) {
            Node* n = path[i]->get();
            upd(n);
            int bf = bfOf(n), key = n->key;
            emit("height", fk(key) + ",\"h\":" + std::to_string(n->h) + ",\"bf\":" + std::to_string(bf));
            string type;
            if (bf > 1) {
                if (bfOf(n->l.get()) >= 0) {
                    rotR(path[i]);
                    type = "LL";
                } else {
                    rotL(&n->l);
                    rotR(path[i]);
                    type = "LR";
                }
            } else if (bf < -1) {
                if (bfOf(n->r.get()) <= 0) {
                    rotL(path[i]);
                    type = "RR";
                } else {
                    rotR(&n->r);
                    rotL(path[i]);
                    type = "RL";
                }
            }
            if (!type.empty()) {
                rotations.push_back({type, key});
                emit("rotate", ",\"type\":\"" + type + "\",\"pivot\":" + std::to_string(key));
            }
        }
    }

    static int fixHeights(Node* n, bool& ok) {
        if (!n) return 0;
        int hl = fixHeights(n->l.get(), ok), hr = fixHeights(n->r.get(), ok);
        n->h = 1 + std::max(hl, hr);
        if (std::abs(hl - hr) > 1) ok = false;
        return n->h;
    }
    static size_t count(const Node* n) { return n ? 1 + count(n->l.get()) + count(n->r.get()) : 0; }
    static void trav(const Node* n, Traversals& t) {
        if (!n) return;
        t.pre.push_back(n->key);
        trav(n->l.get(), t);
        t.in.push_back(n->key);
        trav(n->r.get(), t);
        t.post.push_back(n->key);
    }
    static void snap(const Node* n, string& o) {
        if (!n) {
            o += "null";
            return;
        }
        o += "{\"k\":" + std::to_string(n->key) + ",\"l\":" + jstr(n->label) +
             ",\"a\":" + (n->active ? "1" : "0") + ",\"h\":" + std::to_string(n->h) +
             ",\"bf\":" + std::to_string(bfOf(n)) + ",\"L\":";
        snap(n->l.get(), o);
        o += ",\"R\":";
        snap(n->r.get(), o);
        o += "}";
    }
    static void writePre(const Node* n, std::ostream& f) {
        if (!n) return;
        string l = n->label;
        for (char& c : l)
            if (c == ';' || c == '\n' || c == '\r') c = ' ';
        f << n->key << ';' << l << ';' << (n->active ? 1 : 0) << '\n';
        writePre(n->l.get(), f);
        writePre(n->r.get(), f);
    }
};


// ---------------------------------------------------------------- JSON plano
struct JV {
    char kind = 'n';  // s cadena, i entero, b booleano, n nulo, x otro
    string s;
    long long i = 0;
};

static void putUtf8(string& o, unsigned cp) {
    if (cp < 0x80) {
        o += static_cast<char>(cp);
    } else if (cp < 0x800) {
        o += static_cast<char>(0xC0 | (cp >> 6));
        o += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        o += static_cast<char>(0xE0 | (cp >> 12));
        o += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        o += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
        o += static_cast<char>(0xF0 | (cp >> 18));
        o += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        o += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        o += static_cast<char>(0x80 | (cp & 0x3F));
    }
}

class JsonParser {
public:
    explicit JsonParser(const string& t) : t_(t) {}
    bool parse(std::map<string, JV>& out, string& err) {
        ws();
        if (!eat('{')) return bad(err, "se esperaba un objeto");
        ws();
        if (eat('}')) return done(err);
        while (true) {
            ws();
            string k;
            if (!str(k)) return bad(err, "se esperaba un nombre de campo");
            ws();
            if (!eat(':')) return bad(err, "falta ':'");
            ws();
            JV v;
            if (!value(v)) return bad(err, "valor no valido (solo se admiten cadenas, enteros y booleanos)");
            out[k] = v;
            ws();
            if (eat(',')) continue;
            if (eat('}')) return done(err);
            return bad(err, "falta ',' o '}'");
        }
    }

private:
    const string& t_;
    size_t p_ = 0;
    bool bad(string& err, const string& m) {
        err = "JSON invalido: " + m;
        return false;
    }
    bool done(string& err) {
        ws();
        if (p_ != t_.size()) return bad(err, "texto sobrante");
        return true;
    }
    void ws() {
        while (p_ < t_.size() && (t_[p_] == ' ' || t_[p_] == '\t' || t_[p_] == '\r' || t_[p_] == '\n')) ++p_;
    }
    bool eat(char c) {
        if (p_ < t_.size() && t_[p_] == c) {
            ++p_;
            return true;
        }
        return false;
    }
    bool lit(const char* w) {
        size_t n = std::string(w).size();
        if (t_.compare(p_, n, w) == 0) {
            p_ += n;
            return true;
        }
        return false;
    }
    bool hex4(unsigned& v) {
        if (p_ + 4 > t_.size()) return false;
        v = 0;
        for (int i = 0; i < 4; ++i) {
            char c = t_[p_++];
            v <<= 4;
            if (c >= '0' && c <= '9') v |= static_cast<unsigned>(c - '0');
            else if (c >= 'a' && c <= 'f') v |= static_cast<unsigned>(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') v |= static_cast<unsigned>(c - 'A' + 10);
            else return false;
        }
        return true;
    }
    bool str(string& o) {
        if (!eat('"')) return false;
        while (p_ < t_.size()) {
            char c = t_[p_++];
            if (c == '"') return true;
            if (c != '\\') {
                o += c;
                continue;
            }
            if (p_ >= t_.size()) return false;
            char e = t_[p_++];
            switch (e) {
                case '"': o += '"'; break;
                case '\\': o += '\\'; break;
                case '/': o += '/'; break;
                case 'b': o += '\b'; break;
                case 'f': o += '\f'; break;
                case 'n': o += '\n'; break;
                case 'r': o += '\r'; break;
                case 't': o += '\t'; break;
                case 'u': {
                    unsigned cp;
                    if (!hex4(cp)) return false;
                    if (cp >= 0xD800 && cp < 0xDC00 && t_.compare(p_, 2, "\\u") == 0) {
                        size_t save = p_;
                        p_ += 2;
                        unsigned lo;
                        if (hex4(lo) && lo >= 0xDC00 && lo < 0xE000)
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        else
                            p_ = save;
                    }
                    putUtf8(o, cp);
                    break;
                }
                default: return false;
            }
        }
        return false;
    }
    bool value(JV& v) {
        if (p_ >= t_.size()) return false;
        char c = t_[p_];
        if (c == '"') {
            v.kind = 's';
            return str(v.s);
        }
        if (lit("true")) { v.kind = 'b'; v.i = 1; return true; }
        if (lit("false")) { v.kind = 'b'; v.i = 0; return true; }
        if (lit("null")) { v.kind = 'n'; return true; }
        size_t st = p_;
        while (p_ < t_.size() && string("+-0123456789.eE").find(t_[p_]) != string::npos) ++p_;
        if (p_ == st) return false;
        string num = t_.substr(st, p_ - st);
        size_t d = (num[0] == '-') ? 1 : 0;
        bool digits = num.size() > d && num.size() - d <= 18;
        for (size_t j = d; j < num.size(); ++j)
            if (num[j] < '0' || num[j] > '9') digits = false;
        if (digits) {
            v.kind = 'i';
            v.i = std::stoll(num);
        } else {
            v.kind = 'x';
        }
        return true;
    }
};

// ---------------------------------------------------------------- motor API
class Engine {
public:
    AvlTree tree;
    bool dirty = false;
    bool stop = false;
    string dataPath = "data/arbol_avl.txt";
    vector<string> history;

    Engine() { tree.record = true; }

    string handle(const string& line) {
        std::map<string, JV> req;
        string err;
        tree.steps.clear();
        if (!JsonParser(line).parse(req, err)) return fail(err);
        auto it = req.find("action");
        if (it == req.end() || it->second.kind != 's') return fail("Falta el campo 'action'");
        const string a = it->second.s;
        string result = "{}";
        const bool mutating = (a == "insert" || a == "delete" || a == "toggle" || a == "update");
        string before = mutating ? tree.serialize() : string();
        int key = 0;
        string label;
        if (!optLabel(req, label, err)) return fail(err);
        if (a == "ping") {
            result = "{\"backend\":\"cpp\",\"protocol\":\"1\"}";
        } else if (a == "state" || a == "traversals") {
        } else if (a == "reset") {
            tree.clear();
            dirty = false;
        } else if (a == "load" || a == "save") {
            string path = dataPath;
            auto p = req.find("path");
            if (p != req.end()) {
                if (p->second.kind != 's') return fail("'path' debe ser texto");
                path = p->second.s;
            }
            if (a == "load" ? !tree.load(path, err) : !tree.save(path, err)) return fail(err);
            dirty = false;
            result = "{\"path\":" + jstr(path) + ",\"size\":" + std::to_string(tree.size()) + "}";
        } else if (a == "undo") {
            if (history.empty()) return fail("No hay nada que deshacer");
            std::istringstream in(history.back());
            history.pop_back();
            if (!tree.loadStream(in, err, "")) return fail(err);
            dirty = true;
        } else if (a == "insert" || a == "delete" || a == "search" || a == "toggle" || a == "update") {
            if (!getKey(req, key, err)) return fail(err);
            string k = std::to_string(key);
            if (a == "insert") {
                if (!tree.insert(key, label, err)) return fail(err);
                dirty = true;
                result = "{\"key\":" + k + "}";
            } else if (a == "delete") {
                if (!tree.erase(key, err)) return fail(err);
                dirty = true;
                result = "{\"key\":" + k + "}";
            } else if (a == "search") {
                const Node* n = tree.search(key);
                result = n ? "{\"found\":true,\"key\":" + k + ",\"label\":" + jstr(n->label) +
                                 ",\"active\":" + (n->active ? "true" : "false") + "}"
                           : "{\"found\":false,\"key\":" + k + "}";
            } else if (a == "toggle") {
                if (!tree.toggle(key, err)) return fail(err);
                dirty = true;
                result = "{\"key\":" + k + ",\"active\":" + (tree.peek(key)->active ? "true" : "false") + "}";
            } else {
                if (!tree.updateLabel(key, label, err)) return fail(err);
                dirty = true;
                result = "{\"key\":" + k + "}";
            }
        } else if (a == "shutdown") {
            stop = true;
        } else {
            return fail("Accion desconocida: " + a);
        }
        if (mutating) {
            history.push_back(std::move(before));
            if (history.size() > 200) history.erase(history.begin());
        }
        return okResp(result);
    }

private:
    string state() const {
        return string("{\"dirty\":") + (dirty ? "true" : "false") + ",\"size\":" + std::to_string(tree.size()) + "}";
    }
    string fail(const string& m) {
        tree.steps.clear();
        return "{\"ok\":false,\"error\":" + jstr(m) + ",\"state\":" + state() + "}";
    }
    static string arr(const vector<int>& v) {
        string o = "[";
        for (size_t i = 0; i < v.size(); ++i) o += (i ? "," : "") + std::to_string(v[i]);
        return o + "]";
    }
    string okResp(const string& result) {
        string o = "{\"ok\":true,\"result\":" + result + ",\"steps\":[";
        for (size_t i = 0; i < tree.steps.size(); ++i) o += (i ? "," : "") + tree.steps[i].json;
        Traversals t = tree.traversals();
        o += "],\"tree\":" + tree.snapshot() + ",\"traversals\":{\"pre\":" + arr(t.pre) +
             ",\"in\":" + arr(t.in) + ",\"post\":" + arr(t.post) + "},\"state\":" + state() + "}";
        return o;
    }
    static bool optLabel(const std::map<string, JV>& req, string& label, string& err) {
        auto l = req.find("label");
        if (l == req.end() || l->second.kind == 'n') return true;
        if (l->second.kind != 's') {
            err = "'label' debe ser texto";
            return false;
        }
        label = l->second.s;
        return true;
    }
    static bool getKey(const std::map<string, JV>& req, int& key, string& err) {
        auto k = req.find("key");
        if (k == req.end()) {
            err = "Falta el campo 'key'";
            return false;
        }
        if (k->second.kind != 'i') {
            err = "'key' debe ser un entero";
            return false;
        }
        if (k->second.i < INT32_MIN || k->second.i > INT32_MAX) {
            err = "Clave fuera de rango int32: " + std::to_string(k->second.i);
            return false;
        }
        key = static_cast<int>(k->second.i);
        return true;
    }
};

// ---------------------------------------------------------------- autoprueba
static int g_fails = 0;
#define CHECK(c)                                                              \
    do {                                                                      \
        if (!(c)) {                                                           \
            ++g_fails;                                                        \
            std::cerr << "FALLO linea " << __LINE__ << ": " #c "\n";          \
        }                                                                     \
    } while (0)

static bool hasStep(const AvlTree& t, const string& fragment) {
    for (const auto& s : t.steps)
        if (s.json.find(fragment) != string::npos) return true;
    return false;
}

static int checkNode(const Node* n, bool& ok) {
    if (!n) return 0;
    int hl = checkNode(n->l.get(), ok), hr = checkNode(n->r.get(), ok);
    int h = 1 + std::max(hl, hr);
    if (h != n->h || std::abs(hl - hr) > 1) ok = false;
    return h;
}
static bool valid(const AvlTree& t) {
    bool ok = true;
    checkNode(t.root.get(), ok);
    return ok;
}

static AvlTree build(const vector<int>& keys, bool rec = false) {
    AvlTree t;
    t.record = rec;
    string e;
    for (int k : keys) t.insert(k, "n" + std::to_string(k), e);
    return t;
}
using V = vector<int>;

static void testRotations() {
    struct C { V keys; string type; int pivot; V pre; };
    vector<C> cases = {{{10, 20, 30}, "RR", 10, {20, 10, 30}},
                       {{30, 20, 10}, "LL", 30, {20, 10, 30}},
                       {{10, 30, 20}, "RL", 10, {20, 10, 30}},
                       {{30, 10, 20}, "LR", 30, {20, 10, 30}}};
    for (auto& c : cases) {
        AvlTree t = build(c.keys, true);
        CHECK(t.traversals().pre == c.pre);
        CHECK(hasStep(t, "\"t\":\"rotate\",\"type\":\"" + c.type + "\",\"pivot\":" +
                             std::to_string(c.pivot) + ","));
        CHECK(valid(t));
        for (const auto& s : t.steps) CHECK(s.json.find("\"tree\":") != string::npos);
    }
    AvlTree t = build({10, 20}, true);
    CHECK(!hasStep(t, "\"t\":\"rotate\""));
    CHECK(hasStep(t, "\"t\":\"place\",\"key\":20,"));
    CHECK(hasStep(t, "\"t\":\"compare\",\"key\":20,\"with\":10,"));
    CHECK(hasStep(t, "\"t\":\"descend\",\"dir\":\"R\","));
}

static void testErase() {
    AvlTree t = build({50, 30, 70, 20, 40, 60, 80});
    string e;
    CHECK(t.erase(20, e));
    CHECK(t.traversals().pre == (V{50, 30, 40, 70, 60, 80}));
    CHECK(t.erase(30, e));
    CHECK(t.traversals().pre == (V{50, 40, 70, 60, 80}));
    t.record = true;
    CHECK(t.erase(50, e));
    CHECK(t.traversals().pre == (V{60, 40, 70, 80}));
    CHECK(hasStep(t, "\"t\":\"replace\",\"key\":50,\"with\":60,"));
    CHECK(hasStep(t, "\"t\":\"remove\",\"key\":60,"));
    CHECK(valid(t));

    AvlTree u = build({2, 1, 3, 4}, false);
    u.record = true;
    CHECK(u.erase(1, e));
    CHECK(hasStep(u, "\"t\":\"rotate\",\"type\":\"RR\",\"pivot\":2,"));
    CHECK(u.traversals().pre == (V{3, 2, 4}));
    CHECK(valid(u));
}

static void testErrors() {
    AvlTree t;
    string e;
    CHECK(!t.erase(1, e) && !e.empty());
    CHECK(!t.toggle(1, e));
    CHECK(!t.updateLabel(1, "x", e));
    CHECK(t.search(1) == nullptr);
    CHECK(t.snapshot() == "null");
    CHECK(t.insert(5, "a", e));
    e.clear();
    CHECK(!t.insert(5, "b", e) && !e.empty());
    CHECK(t.size() == 1);
    e.clear();
    CHECK(!t.erase(9, e) && !e.empty());
    CHECK(t.search(5) && t.search(5)->label == "a");
    CHECK(t.toggle(5, e) && !t.search(5)->active);
    CHECK(t.toggle(5, e) && t.search(5)->active);
    CHECK(t.updateLabel(5, "z", e) && t.search(5)->label == "z");
    CHECK(t.snapshot().rfind("{\"k\":5,\"l\":\"z\",\"a\":1,\"h\":1,\"bf\":0,", 0) == 0);
    t.clear();
    CHECK(t.size() == 0);
}

static void testBig() {
    AvlTree t;
    string e;
    for (int i = 1; i <= 1000; ++i) CHECK(t.insert(i, "", e));
    CHECK(valid(t));
    CHECK(t.root->h <= 1.44 * std::log2(1000.0) + 1e-9);
    CHECK(t.size() == 1000);
    unsigned s = 12345;
    for (int i = 0; i < 3000; ++i) {
        s = s * 1103515245u + 12345u;
        int k = static_cast<int>((s >> 8) % 1500);
        if (s & 0x1000000) t.insert(k, "", e); else t.erase(k, e);
        if (!valid(t)) { CHECK(false); break; }
    }
    auto tr = t.traversals();
    CHECK(std::is_sorted(tr.in.begin(), tr.in.end()));
    CHECK(tr.pre.size() == t.size() && tr.post.size() == t.size());
}

static void testPersistence() {
    auto dir = std::filesystem::temp_directory_path() / "paa_selftest";
    std::filesystem::create_directories(dir);
    string f = (dir / "a.txt").string(), e;
    AvlTree t = build({50, 30, 70, 20, 40, -5, 0, 2147483647});
    string e2;
    t.insert(99, "a;b\nc", e2);
    t.toggle(30, e2);
    CHECK(t.save(f, e));
    AvlTree u;
    CHECK(u.load(f, e));
    CHECK(u.traversals().pre == t.traversals().pre);
    CHECK(u.search(99) && u.search(99)->label == "a b c");
    CHECK(u.search(30) && !u.search(30)->active);
    CHECK(u.search(50) && u.search(50)->active);

    string bad = (dir / "b.txt").string();
    { std::ofstream o(bad); o << "1;a;1\nbasura\n"; }
    CHECK(!u.load(bad, e) && !e.empty());
    CHECK(u.traversals().pre == t.traversals().pre);
    { std::ofstream o(bad); o << ""; }
    CHECK(!u.load(bad, e));
    { std::ofstream o(bad); o << "1;a;1\n1;b;1\n"; }
    CHECK(!u.load(bad, e));
    { std::ofstream o(bad); o << "1;a;7\n"; }
    CHECK(!u.load(bad, e));
    { std::ofstream o(bad); o << "1;a;1\n2;b;1\n3;c;1\n"; }
    CHECK(u.load(bad, e) && u.traversals().pre == (V{2, 1, 3}) && valid(u));
    CHECK(u.load(f, e));
    CHECK(!u.load((dir / "no_existe.txt").string(), e));
    CHECK(u.traversals().pre == t.traversals().pre);
    std::filesystem::remove_all(dir);
}

static int selfTest() {
    testRotations();
    testErase();
    testErrors();
    testBig();
    testPersistence();
    if (g_fails) {
        std::cout << "FALLO (" << g_fails << ")\n";
        return 1;
    }
    std::cout << "OK\n";
    return 0;
}

// ---------------------------------------------------------------- consola
static void gotoxy(int row, int col) { std::cout << "\x1b[" << row << ";" << col << "H"; }

static int Node_h(const Node* n) { return n ? n->h : 0; }

struct Pos { int idx, depth; };

static void layout(const Node* n, int depth, int& next, std::map<const Node*, Pos>& pos, int& maxDepth) {
    if (!n) return;
    layout(n->l.get(), depth + 1, next, pos, maxDepth);
    pos[n] = {next++, depth};
    maxDepth = std::max(maxDepth, depth);
    layout(n->r.get(), depth + 1, next, pos, maxDepth);
}

static int drawTree(const AvlTree& t) {
    std::cout << "\x1b[2J\x1b[H";
    gotoxy(1, 1);
    std::cout << "PAA - Arbol AVL";
    if (!t.root) {
        gotoxy(3, 1);
        std::cout << "(arbol vacio)";
        return 5;
    }
    std::map<const Node*, Pos> pos;
    int next = 0, maxDepth = 0;
    layout(t.root.get(), 0, next, pos, maxDepth);
    size_t w = 0;
    for (const auto& kv : pos) w = std::max(w, std::to_string(kv.first->key).size());
    int cell = static_cast<int>(w) + 3;
    auto center = [&](const Node* n) { return pos[n].idx * cell + 2 + static_cast<int>(w) / 2; };
    for (const auto& kv : pos) {
        const Node* n = kv.first;
        int row = 3 + kv.second.depth * 3;
        string k = std::to_string(n->key);
        int c = center(n);
        gotoxy(row, c - static_cast<int>(k.size()) / 2);
        std::cout << (n->active ? "\x1b[1m" : "\x1b[90m") << k << "\x1b[0m";
        int bf = (Node_h(n->l.get()) - Node_h(n->r.get()));
        string b = (bf > 0 ? "+" : "") + std::to_string(bf);
        gotoxy(row + 1, c - static_cast<int>(b.size()) / 2);
        std::cout << "\x1b[36m" << b << "\x1b[0m";
        for (int side = 0; side < 2; ++side) {
            const Node* ch = side ? n->r.get() : n->l.get();
            if (!ch) continue;
            gotoxy(row + 2, (c + center(ch)) / 2);
            std::cout << (side ? '\\' : '/');
        }
    }
    return 3 + (maxDepth + 1) * 3 + 1;
}

static string joinKeys(const vector<int>& v) {
    string o;
    for (size_t i = 0; i < v.size(); ++i) o += (i ? ", " : "") + std::to_string(v[i]);
    return o.empty() ? "-" : o;
}

static bool readLine(const string& prompt, string& out) {
    std::cout << prompt << std::flush;
    return static_cast<bool>(std::getline(std::cin, out));
}
static bool readKey(const string& prompt, int& key, bool& eof) {
    string s;
    if (!readLine(prompt, s)) {
        eof = true;
        return false;
    }
    while (!s.empty() && (s.back() == ' ' || s.back() == '\r')) s.pop_back();
    while (!s.empty() && s[0] == ' ') s.erase(0, 1);
    return parseInt32(s, key);
}

static int runConsole(const string& dataPath) {
    AvlTree tree;
    tree.record = false;
    bool dirty = false, eof = false;
    string msg, in;
    std::cout << "PAA - Programa de Aprendizaje de Arboles AVL\n";
    if (!readLine("Cargar datos de '" + dataPath + "'? (s/n): ", in)) return 0;
    if (!in.empty() && (in[0] == 's' || in[0] == 'S')) {
        string e;
        msg = tree.load(dataPath, e) ? "Datos cargados (" + std::to_string(tree.size()) + " nodos)." : "No se cargo: " + e;
    } else {
        msg = "Arbol vacio.";
    }
    while (!eof) {
        int row = drawTree(tree);
        Traversals tr = tree.traversals();
        gotoxy(row, 1);
        std::cout << "Preorden : " << joinKeys(tr.pre) << "\nInorden  : " << joinKeys(tr.in)
                  << "\nPostorden: " << joinKeys(tr.post) << "\n\n";
        if (!msg.empty()) std::cout << ">> " << msg << "\n\n";
        std::cout << "1) Insertar  2) Eliminar  3) Buscar  4) Desactivar/reactivar\n"
                     "5) Modificar etiqueta  6) Guardar  7) Cargar  8) Nuevo  0) Salir\n";
        if (!readLine("Opcion: ", in)) break;
        msg.clear();
        int key = 0;
        string e, label;
        if (in == "0") {
            if (dirty && readLine("Hay cambios sin guardar. Guardar? (s/n): ", in) && !in.empty() &&
                (in[0] == 's' || in[0] == 'S')) {
                if (!tree.save(dataPath, e)) std::cout << "No se guardo: " << e << "\n";
            }
            break;
        } else if (in == "1" || in == "2" || in == "3" || in == "4" || in == "5") {
            if (!readKey("Clave (entero): ", key, eof)) {
                msg = eof ? "" : "Clave invalida: debe ser un entero de 32 bits.";
                continue;
            }
            if (in == "1" || in == "5") readLine("Etiqueta: ", label);
            bool ok = false;
            if (in == "1") {
                ok = tree.insert(key, label, e);
                if (ok) msg = "Insertado " + std::to_string(key) + ".";
            } else if (in == "2") {
                ok = tree.erase(key, e);
                if (ok) msg = "Eliminado " + std::to_string(key) + ".";
            } else if (in == "3") {
                const Node* n = tree.search(key);
                msg = n ? "Encontrado " + std::to_string(key) + " etiqueta '" + n->label + "' (" +
                              (n->active ? "activo" : "inactivo") + ")."
                        : "No existe la clave " + std::to_string(key) + ".";
                continue;
            } else if (in == "4") {
                ok = tree.toggle(key, e);
                if (ok) msg = string("Nodo ") + std::to_string(key) + (tree.peek(key)->active ? " reactivado." : " desactivado.");
            } else {
                ok = tree.updateLabel(key, label, e);
                if (ok) msg = "Etiqueta modificada.";
            }
            if (!ok) {
                msg = e;
            } else {
                dirty = true;
                for (const auto& r : tree.rotations)
                    msg += " Rotacion " + r.first + " en " + std::to_string(r.second) + ".";
            }
        } else if (in == "6" || in == "7") {
            string p = dataPath, alt;
            if (readLine("Ruta [" + dataPath + "]: ", alt) && !alt.empty()) p = alt;
            if (in == "6") {
                msg = tree.save(p, e) ? "Guardado en " + p + "." : e;
                if (msg[0] == 'G') dirty = false;
            } else {
                msg = tree.load(p, e) ? "Cargado desde " + p + "." : e;
                if (msg[0] == 'C') dirty = false;
            }
        } else if (in == "8") {
            tree.clear();
            dirty = false;
            msg = "Arbol nuevo.";
        } else {
            msg = "Opcion no valida.";
        }
    }
    std::cout << "\nHasta luego.\n";
    return 0;
}

static int runApi(const string& dataPath) {
    std::ios::sync_with_stdio(false);
    Engine eng;
    eng.dataPath = dataPath;
    string line;
    while (!eng.stop && std::getline(std::cin, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        std::cout << eng.handle(line) << '\n' << std::flush;
    }
    return 0;
}

#ifdef _WIN32
#include <windows.h>
static void initTerminal() {
    SetConsoleOutputCP(65001);
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD m = 0;
    if (GetConsoleMode(h, &m)) SetConsoleMode(h, m | 0x0004);
}
#else
static void initTerminal() {}
#endif

int main(int argc, char** argv) {
    bool api = false;
    string data = "data/arbol_avl.txt";
    for (int i = 1; i < argc; ++i) {
        string a = argv[i];
        if (a == "--self-test") return selfTest();
        if (a == "--api") api = true;
        else if (a == "--data" && i + 1 < argc) data = argv[++i];
        else if (a == "--help" || a == "-h") {
            std::cout << "Uso: paa_cpp [--api] [--data ruta] [--self-test]\n";
            return 0;
        }
    }
    if (api) return runApi(data);
    initTerminal();
    return runConsole(data);
}
