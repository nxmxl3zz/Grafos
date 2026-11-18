// PERA - Programa Estadístico de Rutas de Automóviles (Parcial 3, REMR). Motor C++17.
// Tres grafos ponderados (distancia, combustible, peajes) sobre las capitales de Colombia.
//
// Secciones: 1 utilidades | 2 JSON plano | 3 modelo | 4 repositorio (CRUD, grafos, archivo, deshacer)
//            5 consulta (Dijkstra) | 6 estadísticas | 7 protocolo --api | 8 autoprueba | 9 consola | 10 main
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using std::string;
using std::vector;
using ll = long long;

// ================================================================ 1. utilidades
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

static string jnum(double v) {
    char b[40];
    std::snprintf(b, sizeof b, "%.15g", v);
    return b;
}
static string jfloat(double v) {  // siempre con punto decimal (86.0)
    string t = jnum(v);
    if (t.find_first_of(".en") == string::npos) t += ".0";
    return t;
}
static string jbool(bool b) { return b ? "true" : "false"; }

// Entero escalado (valor*10^dec) a texto con dec decimales exactos.
static string fixedScaled(ll v, int dec) {
    ll p = 1;
    for (int i = 0; i < dec; ++i) p *= 10;
    string sign = v < 0 ? "-" : "";
    ll a = v < 0 ? -v : v;
    string frac = std::to_string(a % p);
    while (static_cast<int>(frac.size()) < dec) frac = "0" + frac;
    return sign + std::to_string(a / p) + (dec ? "." + frac : "");
}

// Texto decimal estricto (-?d+(.d+)?) a double.
static bool parseDecimal(const string& s, double& out) {
    if (s.empty() || s.size() > 24) return false;
    size_t i = (s[0] == '-') ? 1 : 0;
    size_t digits = 0, dots = 0;
    for (size_t j = i; j < s.size(); ++j) {
        if (s[j] >= '0' && s[j] <= '9') ++digits;
        else if (s[j] == '.' && ++dots == 1 && j > i && j + 1 < s.size()) continue;
        else return false;
    }
    if (digits == 0) return false;
    out = std::strtod(s.c_str(), nullptr);
    return std::isfinite(out);
}

static bool toScaled(double v, ll scale, ll lo, ll hi, ll& out) {
    if (!std::isfinite(v) || std::fabs(v) > 1e12) return false;
    ll r = static_cast<ll>(std::floor(v * static_cast<double>(scale) + 0.5));
    if (r < lo || r > hi) return false;
    out = r;
    return true;
}

static string sanitize(string s) {
    for (char& c : s)
        if (c == ';' || c == '\n' || c == '\r') c = ' ';
    return s;
}

static vector<string> splitBy(const string& s, char sep) {
    vector<string> o;
    size_t a = 0;
    while (true) {
        size_t b = s.find(sep, a);
        if (b == string::npos) {
            o.push_back(s.substr(a));
            return o;
        }
        o.push_back(s.substr(a, b - a));
        a = b + 1;
    }
}

static string joinBy(const vector<string>& v, char sep) {
    string o;
    for (size_t i = 0; i < v.size(); ++i) o += (i ? string(1, sep) : string()) + v[i];
    return o;
}

// Límites de los campos (valores escalados).
static const ll LAT_MAX = 9000000, LON_MAX = 18000000;  // grados * 1e5
static const ll KM_MAX = 10000000, HORAS_MAX = 100000000, DINERO_MAX = 1000000000, VEL_MAX = 1000000;
static const ll CONSUMO_MAX = 1000000;

// ================================================================ 2. JSON plano
struct JV {
    char kind = 'n';  // s cadena, i entero, d decimal, b booleano, n nulo, x otro
    string s;
    ll i = 0;
    double d = 0;
    vector<string> list;  // kind 'a': arreglo plano de cadenas/números
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
        if (p_ < t_.size() && string("[\"-0123456789tfn").find(t_[p_]) != string::npos) {
            err = "La solicitud debe ser un objeto JSON";
            return false;
        }
        if (!eat('{')) return bad(err, "");
        ws();
        if (eat('}')) return done(err);
        while (true) {
            ws();
            string k;
            if (!str(k)) return bad(err, "");
            ws();
            if (!eat(':')) return bad(err, "");
            ws();
            JV v;
            if (!value(v)) return bad(err, "");
            out[k] = v;
            ws();
            if (eat(',')) continue;
            if (eat('}')) return done(err);
            return bad(err, "");
        }
    }

private:
    const string& t_;
    size_t p_ = 0;
    bool bad(string& err, const string& m) {
        (void)m;
        err = "JSON inválido";
        return false;
    }
    bool done(string& err) {
        ws();
        if (p_ != t_.size()) return bad(err, "");
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
        if (c == '[') {
            ++p_;
            v.kind = 'a';
            ws();
            if (eat(']')) return true;
            while (true) {
                ws();
                JV e;
                if (!value(e) || e.kind == 'a' || (e.kind != 's' && e.kind != 'i' && e.kind != 'd')) return false;
                v.list.push_back(e.kind == 's' ? e.s : e.kind == 'i' ? std::to_string(e.i) : e.s);
                ws();
                if (eat(',')) continue;
                return eat(']');
            }
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
            v.d = static_cast<double>(v.i);
            return true;
        }
        char* end = nullptr;
        double x = std::strtod(num.c_str(), &end);
        if (*end == 0 && std::isfinite(x)) {
            v.kind = 'd';
            v.d = x;
            v.s = num;
        } else {
            v.kind = 'x';
        }
        return true;
    }
};

// ================================================================ 3. modelo
struct Params {
    ll consumo_x10 = 400;  // km por galón * 10
    ll precio = 16000;     // COP por galón
    ll velocidad = 55;     // km/h
};

struct City {
    string id, nombre, departamento;
    ll lat = 0, lon = 0;  // grados * 1e5
    bool activo = true;
};

struct Toll {
    string id, nombre;
    ll lat = 0, lon = 0, tarifa = 0;
    bool activo = true;
};

struct Route {
    string id, origen, destino;
    ll km_x10 = 0, horas_x100 = 0;
    vector<string> peajes;
    bool activo = true;
};

struct State {
    Params p;
    std::map<string, City> cities;
    std::map<string, Toll> tolls;
    std::map<string, Route> routes;
};

struct Edge {
    string to, rid;
    ll w = 0;      // peso del grafo (km*10, pesos de combustible o pesos de peajes)
    ll horas = 0;  // horas*100, viaja en la arista
};
struct Graph {
    std::map<string, vector<Edge>> adj;  // vecinos por id de ruta ascendente
};

struct CityPatch {
    std::optional<string> nombre, departamento;
    std::optional<ll> lat, lon;
    std::optional<bool> activo;
};
struct TollPatch {
    std::optional<string> nombre;
    std::optional<ll> lat, lon, tarifa;
    std::optional<bool> activo;
};
struct RoutePatch {
    std::optional<string> origen, destino;
    std::optional<ll> km_x10, horas_x100;
    std::optional<vector<string>> peajes;
    std::optional<bool> activo;
};

struct PathRes {
    vector<string> cities, routes;
    ll km_x10 = 0, horas_x100 = 0, combustible = 0, peajes = 0;
};
static const char* const CRIT[4] = {"distancia", "tiempo", "combustible", "peajes"};
static const char* const CRIT_Q[5] = {"distancia", "tiempo", "combustible", "peajes", "total"};
struct QueryRes {
    bool reachable = false;
    PathRes by[5];
};

struct Series {
    ll scale = 1, n = 0, mn = 0, mx = 0, total = 0;
    double media = 0, mediana = 0;
    vector<double> limites;
    vector<ll> cuentas;
};
struct DeptRow { string departamento; ll cantidad = 0, tarifa_total = 0; };
struct DegRow { string id, nombre; ll grado = 0; };
struct TopRow { string id, origen, destino; double valor = 0; };
struct Stats {
    ll ciudades = 0, ciudades_activas = 0, peajes = 0, peajes_activos = 0;
    ll rutas = 0, rutas_activas = 0, rutas_efectivas = 0, componentes = 0;
    Series series[4];
    vector<DeptRow> deptos;
    vector<DegRow> grados;
    vector<TopRow> top[4];
};

// ================================================================ 4. repositorio
class Pera {
public:
    State st;
    Graph gDistancia, gCombustible, gPeajes, gTotal;
    bool dirty = false;
    vector<State> history;

    Pera() { rebuild(); }

    // ---- derivados
    ll fuelOf(ll km_x10) const {
        return (2 * km_x10 * st.p.precio + st.p.consumo_x10) / (2 * st.p.consumo_x10);
    }
    ll tollCost(const Route& r) const {
        ll t = 0;
        for (const auto& id : r.peajes) {
            auto it = st.tolls.find(id);
            if (it != st.tolls.end() && it->second.activo) t += it->second.tarifa;
        }
        return t;
    }
    bool effective(const Route& r) const {
        auto a = st.cities.find(r.origen), b = st.cities.find(r.destino);
        return r.activo && a != st.cities.end() && b != st.cities.end() && a->second.activo && b->second.activo;
    }
    ll degree(const string& cityId) const {
        auto it = gDistancia.adj.find(cityId);
        return it == gDistancia.adj.end() ? 0 : static_cast<ll>(it->second.size());
    }

    // ---- ciudades
    bool createCity(const City& c, string& err) {
        if (st.cities.count(c.id)) return fail(err, "La ciudad " + c.id + " ya existe");
        State before = st;
        st.cities[c.id] = c;
        commit(std::move(before));
        return true;
    }
    bool updateCity(const string& id, const CityPatch& pt, string& err) {
        auto it = st.cities.find(id);
        if (it == st.cities.end()) return fail(err, "La ciudad " + id + " no existe");
        State before = st;
        City& c = it->second;
        if (pt.nombre) c.nombre = *pt.nombre;
        if (pt.departamento) c.departamento = *pt.departamento;
        if (pt.lat) c.lat = *pt.lat;
        if (pt.lon) c.lon = *pt.lon;
        if (pt.activo) c.activo = *pt.activo;
        commit(std::move(before));
        return true;
    }
    bool deleteCity(const string& id, vector<string>& removed, string& err) {
        if (!st.cities.count(id)) return fail(err, "La ciudad " + id + " no existe");
        State before = st;
        for (auto it = st.routes.begin(); it != st.routes.end();) {
            if (it->second.origen == id || it->second.destino == id) {
                removed.push_back(it->first);
                it = st.routes.erase(it);
            } else {
                ++it;
            }
        }
        st.cities.erase(id);
        commit(std::move(before));
        return true;
    }
    bool toggleCity(const string& id, string& err) {
        CityPatch p;
        auto it = st.cities.find(id);
        if (it == st.cities.end()) return fail(err, "La ciudad " + id + " no existe");
        p.activo = !it->second.activo;
        return updateCity(id, p, err);
    }

    // ---- peajes
    string nextId(char prefix, bool toll) const {
        ll mx = 0;
        auto scan = [&](const string& id) {
            if (id.size() < 2 || id[0] != prefix) return;
            for (size_t i = 1; i < id.size(); ++i)
                if (id[i] < '0' || id[i] > '9') return;
            if (id.size() > 16) return;
            mx = std::max(mx, std::stoll(id.substr(1)));
        };
        if (toll) for (const auto& kv : st.tolls) scan(kv.first);
        else for (const auto& kv : st.routes) scan(kv.first);
        char b[24];
        std::snprintf(b, sizeof b, "%c%03lld", prefix, mx + 1);
        return b;
    }
    bool createToll(Toll t, string& err) {
        if (t.id.empty()) t.id = nextId('P', true);
        if (st.tolls.count(t.id)) return fail(err, "El peaje " + t.id + " ya existe");
        State before = st;
        st.tolls[t.id] = t;
        commit(std::move(before));
        return true;
    }
    bool updateToll(const string& id, const TollPatch& pt, string& err) {
        auto it = st.tolls.find(id);
        if (it == st.tolls.end()) return fail(err, "El peaje " + id + " no existe");
        State before = st;
        Toll& t = it->second;
        if (pt.nombre) t.nombre = *pt.nombre;
        if (pt.lat) t.lat = *pt.lat;
        if (pt.lon) t.lon = *pt.lon;
        if (pt.tarifa) t.tarifa = *pt.tarifa;
        if (pt.activo) t.activo = *pt.activo;
        commit(std::move(before));
        return true;
    }
    bool deleteToll(const string& id, string& err) {
        if (!st.tolls.count(id)) return fail(err, "El peaje " + id + " no existe");
        State before = st;
        st.tolls.erase(id);
        for (auto& kv : st.routes) {
            auto& v = kv.second.peajes;
            v.erase(std::remove(v.begin(), v.end(), id), v.end());
        }
        commit(std::move(before));
        return true;
    }
    bool toggleToll(const string& id, string& err) {
        auto it = st.tolls.find(id);
        if (it == st.tolls.end()) return fail(err, "El peaje " + id + " no existe");
        TollPatch p;
        p.activo = !it->second.activo;
        return updateToll(id, p, err);
    }

    // ---- rutas
    static bool checkRoute(const State& s, const Route& r, string& err) {
        if (r.origen == r.destino) return fail(err, "Una ruta necesita dos ciudades distintas");
        if (!s.cities.count(r.origen)) return fail(err, "La ciudad " + r.origen + " no existe");
        if (!s.cities.count(r.destino)) return fail(err, "La ciudad " + r.destino + " no existe");
        for (const auto& t : r.peajes)
            if (!s.tolls.count(t)) return fail(err, "El peaje " + t + " no existe");
        for (const auto& kv : s.routes) {
            const Route& o = kv.second;
            if (o.id == r.id) continue;
            if ((o.origen == r.origen && o.destino == r.destino) || (o.origen == r.destino && o.destino == r.origen))
                return fail(err, "La ruta entre " + r.origen + " y " + r.destino + " ya existe");
        }
        return true;
    }
    bool createRoute(Route r, string& err) {
        if (r.id.empty()) r.id = nextId('R', false);
        if (st.routes.count(r.id)) return fail(err, "La ruta " + r.id + " ya existe");
        if (!checkRoute(st, r, err)) return false;
        State before = st;
        st.routes[r.id] = r;
        commit(std::move(before));
        return true;
    }
    bool updateRoute(const string& id, const RoutePatch& pt, string& err) {
        auto it = st.routes.find(id);
        if (it == st.routes.end()) return fail(err, "La ruta " + id + " no existe");
        Route r = it->second;
        if (pt.origen) r.origen = *pt.origen;
        if (pt.destino) r.destino = *pt.destino;
        if (pt.km_x10) r.km_x10 = *pt.km_x10;
        if (pt.horas_x100) r.horas_x100 = *pt.horas_x100;
        if (pt.peajes) r.peajes = *pt.peajes;
        if (pt.activo) r.activo = *pt.activo;
        if (!checkRoute(st, r, err)) return false;
        State before = st;
        it->second = r;
        commit(std::move(before));
        return true;
    }
    bool deleteRoute(const string& id, string& err) {
        if (!st.routes.count(id)) return fail(err, "La ruta " + id + " no existe");
        State before = st;
        st.routes.erase(id);
        commit(std::move(before));
        return true;
    }
    bool toggleRoute(const string& id, string& err) {
        auto it = st.routes.find(id);
        if (it == st.routes.end()) return fail(err, "La ruta " + id + " no existe");
        RoutePatch p;
        p.activo = !it->second.activo;
        return updateRoute(id, p, err);
    }

    // ---- parámetros (los que no se envían se conservan)
    void setParams(std::optional<ll> consumo_x10, std::optional<ll> precio, std::optional<ll> velocidad) {
        State before = st;
        if (consumo_x10) st.p.consumo_x10 = *consumo_x10;
        if (precio) st.p.precio = *precio;
        if (velocidad) st.p.velocidad = *velocidad;
        commit(std::move(before));
    }

    // ---- deshacer / reiniciar
    bool undo(string& err) {
        if (history.empty()) return fail(err, "No hay nada que deshacer");
        st = std::move(history.back());
        history.pop_back();
        dirty = true;
        rebuild();
        return true;
    }
    void reset() {
        st = State();
        history.clear();
        dirty = false;
        rebuild();
    }

    // ---- archivo
    string serialize() const {
        std::ostringstream o;
        o << "# PERA v1\n";
        o << "K;consumo_km_gal;" << fixedScaled(st.p.consumo_x10, 1) << '\n';
        o << "K;precio_gal;" << st.p.precio << '\n';
        o << "K;velocidad_kmh;" << st.p.velocidad << '\n';
        for (const auto& kv : st.cities) {
            const City& c = kv.second;
            o << "C;" << c.id << ';' << sanitize(c.nombre) << ';' << sanitize(c.departamento) << ';'
              << fixedScaled(c.lat, 5) << ';' << fixedScaled(c.lon, 5) << ';' << (c.activo ? 1 : 0) << '\n';
        }
        for (const auto& kv : st.tolls) {
            const Toll& t = kv.second;
            o << "P;" << t.id << ';' << sanitize(t.nombre) << ';' << fixedScaled(t.lat, 5) << ';'
              << fixedScaled(t.lon, 5) << ';' << t.tarifa << ';' << (t.activo ? 1 : 0) << '\n';
        }
        for (const auto& kv : st.routes) {
            const Route& r = kv.second;
            o << "R;" << r.id << ';' << r.origen << ';' << r.destino << ';' << fixedScaled(r.km_x10, 1) << ';'
              << fixedScaled(r.horas_x100, 2) << ';' << joinBy(r.peajes, '|') << ';' << (r.activo ? 1 : 0) << '\n';
        }
        return o.str();
    }

    bool save(const string& path, string& err) {
        std::filesystem::path p(path), tmp(path + ".tmp");
        std::error_code ec;
        if (p.has_parent_path()) std::filesystem::create_directories(p.parent_path(), ec);
        {
            std::ofstream f(tmp, std::ios::binary);
            if (!f) return fail(err, "No se pudo escribir el archivo: " + path);
            f << serialize();
            f.flush();
            if (!f) return fail(err, "Error al escribir el archivo: " + path);
        }
        std::filesystem::rename(tmp, p, ec);
        if (ec) {
            std::filesystem::remove(tmp, ec);
            return fail(err, "No se pudo escribir el archivo: " + path);
        }
        dirty = false;
        return true;
    }

    // Atómico: si hay error el estado queda intacto.
    bool load(const string& path, string& err) {
        std::ifstream f(path, std::ios::binary);
        if (!f) return fail(err, "Archivo inválido: no se pudo abrir " + path);
        State s;
        if (!parseState(f, s, err)) return false;
        st = std::move(s);
        history.clear();
        dirty = false;
        rebuild();
        return true;
    }

    static bool parseState(std::istream& in, State& out, string& err) {
        struct RRec { Route r; int line; };
        vector<RRec> rrecs;
        State s;
        std::set<string> kSeen;
        string line;
        int ln = 0;
        auto bad = [&](const string& m) {
            err = "Archivo inválido: línea " + std::to_string(ln) + ": " + m;
            return false;
        };
        auto flag = [](const string& x, bool& b) {
            if (x != "0" && x != "1") return false;
            b = x == "1";
            return true;
        };
        auto idOk = [](const string& x) {
            return !x.empty() && x.find_first_of(";|\r\n") == string::npos;
        };
        auto dec = [](const string& x, ll scale, ll lo, ll hi, ll& o) {
            double d;
            return parseDecimal(x, d) && toScaled(d, scale, lo, hi, o);
        };
        while (std::getline(in, line)) {
            ++ln;
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty() || line[0] == '#') continue;
            vector<string> f = splitBy(line, ';');
            const string& t = f[0];
            if (t == "K") {
                if (f.size() != 3) return bad("registro K mal formado");
                ll v = 0;
                if (!kSeen.insert(f[1]).second) return bad("parámetro repetido " + f[1]);
                if (f[1] == "consumo_km_gal") {
                    if (!dec(f[2], 10, 1, CONSUMO_MAX, v)) return bad("consumo_km_gal fuera de rango");
                    s.p.consumo_x10 = v;
                } else if (f[1] == "precio_gal") {
                    if (!dec(f[2], 1, 0, DINERO_MAX, v) || f[2].find('.') != string::npos)
                        return bad("precio_gal fuera de rango");
                    s.p.precio = v;
                } else if (f[1] == "velocidad_kmh") {
                    if (!dec(f[2], 1, 1, VEL_MAX, v) || f[2].find('.') != string::npos)
                        return bad("velocidad_kmh fuera de rango");
                    s.p.velocidad = v;
                } else {
                    return bad("parámetro desconocido " + f[1]);
                }
            } else if (t == "C") {
                if (f.size() != 7) return bad("registro C mal formado");
                City c;
                c.id = f[1];
                c.nombre = f[2];
                c.departamento = f[3];
                if (!idOk(c.id)) return bad("id de ciudad inválido");
                if (!dec(f[4], 100000, -LAT_MAX, LAT_MAX, c.lat) || !dec(f[5], 100000, -LON_MAX, LON_MAX, c.lon))
                    return bad("coordenadas fuera de rango");
                if (!flag(f[6], c.activo)) return bad("activo debe ser 0 o 1");
                if (s.cities.count(c.id)) return bad("id repetido " + c.id);
                s.cities[c.id] = c;
            } else if (t == "P") {
                if (f.size() != 7) return bad("registro P mal formado");
                Toll p;
                p.id = f[1];
                p.nombre = f[2];
                if (!idOk(p.id)) return bad("id de peaje inválido");
                if (!dec(f[3], 100000, -LAT_MAX, LAT_MAX, p.lat) || !dec(f[4], 100000, -LON_MAX, LON_MAX, p.lon))
                    return bad("coordenadas fuera de rango");
                if (!dec(f[5], 1, 0, DINERO_MAX, p.tarifa) || f[5].find('.') != string::npos)
                    return bad("tarifa fuera de rango");
                if (!flag(f[6], p.activo)) return bad("activo debe ser 0 o 1");
                if (s.tolls.count(p.id)) return bad("id repetido " + p.id);
                s.tolls[p.id] = p;
            } else if (t == "R") {
                if (f.size() != 8) return bad("registro R mal formado");
                Route r;
                r.id = f[1];
                r.origen = f[2];
                r.destino = f[3];
                if (!idOk(r.id)) return bad("id de ruta inválido");
                if (!dec(f[4], 10, 1, KM_MAX, r.km_x10)) return bad("km fuera de rango");
                if (!dec(f[5], 100, 1, HORAS_MAX, r.horas_x100)) return bad("horas fuera de rango");
                if (!f[6].empty()) {
                    r.peajes = splitBy(f[6], '|');
                    for (const auto& x : r.peajes)
                        if (x.empty()) return bad("lista de peajes mal formada");
                    std::set<string> uniq(r.peajes.begin(), r.peajes.end());
                    if (uniq.size() != r.peajes.size()) return bad("peaje repetido en la ruta");
                }
                if (!flag(f[7], r.activo)) return bad("activo debe ser 0 o 1");
                for (const auto& q : rrecs)
                    if (q.r.id == r.id) return bad("id repetido " + r.id);
                rrecs.push_back({r, ln});
            } else {
                return bad("tipo de registro desconocido");
            }
        }
        for (const auto& q : rrecs) {
            ln = q.line;
            string e;
            if (!checkRoute(s, q.r, e)) return bad(e);
            s.routes[q.r.id] = q.r;
        }
        out = std::move(s);
        return true;
    }

    // ---- grafos (se reescriben tras cada cambio)
    void rebuild() {
        gDistancia.adj.clear();
        gCombustible.adj.clear();
        gPeajes.adj.clear();
        gTotal.adj.clear();
        for (const auto& kv : st.cities) {
            gDistancia.adj[kv.first];
            gCombustible.adj[kv.first];
            gPeajes.adj[kv.first];
            gTotal.adj[kv.first];
        }
        // Desempate lexicografico (costo, km): peso = costo*M + km_x10 con M > suma de TODOS los km_x10; si el producto
        // desbordara se usa solo el costo (misma regla que el motor Python).
        ll kmSum = 0;
        __int128 costSum = 0;
        for (const auto& kv : st.routes) {
            if (!effective(kv.second)) continue;
            kmSum += kv.second.km_x10;
            costSum += fuelOf(kv.second.km_x10) + tollCost(kv.second);
        }
        ll tieM = kmSum + 1;
        if ((costSum + 1) * static_cast<__int128>(tieM) >= static_cast<__int128>(4000000000000000000LL)) tieM = 0;
        for (const auto& kv : st.routes) {
            const Route& r = kv.second;
            if (!effective(r)) continue;
            ll fuel = fuelOf(r.km_x10), tolls = tollCost(r);
            auto add = [&](Graph& g, ll w) {
                g.adj[r.origen].push_back({r.destino, r.id, w, r.horas_x100});
                g.adj[r.destino].push_back({r.origen, r.id, w, r.horas_x100});
            };
            add(gDistancia, r.km_x10);
            add(gCombustible, fuel);
            add(gPeajes, tieM ? tolls * tieM + r.km_x10 : tolls);
            add(gTotal, tieM ? (fuel + tolls) * tieM + r.km_x10 : fuel + tolls);
        }
    }

    // ---- consulta (sección 5)
    bool query(const string& from, const string& to, QueryRes& q, string& err) const;
    Stats stats() const;

    static bool fail(string& err, const string& m) {
        err = m;
        return false;
    }

private:
    void commit(State&& before) {
        history.push_back(std::move(before));
        if (history.size() > 200) history.erase(history.begin());
        dirty = true;
        rebuild();
    }
};

// ================================================================ 5. consulta (Dijkstra determinista)
// Cola ordenada por (costo, id de ciudad); relaja solo si el costo es estrictamente menor;
// vecinos por id de ruta ascendente.
static bool dijkstra(const Graph& g, bool byTime, const string& from, const string& to, vector<string>& cities,
                     vector<string>& routes) {
    std::map<string, ll> dist;
    std::map<string, std::pair<string, string>> prev;  // ciudad -> (ciudad previa, ruta)
    std::set<std::pair<ll, string>> pq;
    dist[from] = 0;
    pq.insert({0, from});
    while (!pq.empty()) {
        std::pair<ll, string> top = *pq.begin();
        pq.erase(pq.begin());
        ll d = top.first;
        const string& u = top.second;
        if (u == to) break;
        auto it = g.adj.find(u);
        if (it == g.adj.end()) continue;
        for (const Edge& e : it->second) {
            ll nd = d + (byTime ? e.horas : e.w);
            auto f = dist.find(e.to);
            if (f == dist.end() || nd < f->second) {
                if (f != dist.end()) pq.erase({f->second, e.to});
                dist[e.to] = nd;
                prev[e.to] = {u, e.rid};
                pq.insert({nd, e.to});
            }
        }
    }
    if (!dist.count(to)) return false;
    cities.clear();
    routes.clear();
    string cur = to;
    cities.push_back(cur);
    while (cur != from) {
        const auto& p = prev[cur];
        routes.push_back(p.second);
        cur = p.first;
        cities.push_back(cur);
    }
    std::reverse(cities.begin(), cities.end());
    std::reverse(routes.begin(), routes.end());
    return true;
}

bool Pera::query(const string& from, const string& to, QueryRes& q, string& err) const {
    auto a = st.cities.find(from), b = st.cities.find(to);
    if (a == st.cities.end()) return fail(err, "La ciudad " + from + " no existe");
    if (b == st.cities.end()) return fail(err, "La ciudad " + to + " no existe");
    if (!a->second.activo) return fail(err, "Ciudad inactiva: " + from);
    if (!b->second.activo) return fail(err, "Ciudad inactiva: " + to);
    q = QueryRes();
    const Graph* gs[5] = {&gDistancia, &gDistancia, &gCombustible, &gPeajes, &gTotal};
    for (int c = 0; c < 5; ++c) {
        PathRes& pr = q.by[c];
        if (!dijkstra(*gs[c], c == 1, from, to, pr.cities, pr.routes)) {
            q.reachable = false;
            return true;
        }
        for (const auto& rid : pr.routes) {
            const Route& r = st.routes.at(rid);
            pr.km_x10 += r.km_x10;
            pr.horas_x100 += r.horas_x100;
            pr.combustible += fuelOf(r.km_x10);
            pr.peajes += tollCost(r);
        }
    }
    q.reachable = true;
    return true;
}

// ================================================================ 6. estadísticas
static Series makeSeries(vector<ll> v, ll scale) {
    Series s;
    s.scale = scale;
    s.n = static_cast<ll>(v.size());
    s.limites.assign(11, 0.0);
    s.cuentas.assign(10, 0);
    if (v.empty()) return s;
    std::sort(v.begin(), v.end());
    s.mn = v.front();
    s.mx = v.back();
    for (ll x : v) s.total += x;
    size_t n = v.size();
    double sc = static_cast<double>(scale);
    // media y límites redondeados a 2 decimales, mitades hacia arriba (aritmética entera exacta)
    ll nn = static_cast<ll>(n);
    s.media = static_cast<double>((s.total * 200 + nn * scale) / (2 * nn * scale)) / 100.0;
    s.mediana = (n % 2 ? static_cast<double>(v[n / 2]) : (static_cast<double>(v[n / 2 - 1]) + static_cast<double>(v[n / 2])) / 2.0) / sc;
    for (int i = 0; i <= 10; ++i)
        s.limites[static_cast<size_t>(i)] =
            static_cast<double>(((s.mn * 10 + (s.mx - s.mn) * i) * 200 + 10 * scale) / (20 * scale)) / 100.0;
    for (ll x : v) {
        ll idx = (s.mx == s.mn) ? 0 : (x - s.mn) * 10 / (s.mx - s.mn);
        s.cuentas[static_cast<size_t>(std::min<ll>(idx, 9))]++;
    }
    return s;
}

Stats Pera::stats() const {
    Stats s;
    s.ciudades = static_cast<ll>(st.cities.size());
    for (const auto& kv : st.cities) s.ciudades_activas += kv.second.activo;
    s.peajes = static_cast<ll>(st.tolls.size());
    for (const auto& kv : st.tolls) s.peajes_activos += kv.second.activo;
    s.rutas = static_cast<ll>(st.routes.size());
    vector<ll> vals[4];
    std::map<string, std::set<string>> deptTolls;
    const ll scales[4] = {10, 100, 1, 1};
    for (const auto& kv : st.routes) {
        const Route& r = kv.second;
        s.rutas_activas += r.activo;
        if (!effective(r)) continue;
        ++s.rutas_efectivas;
        ll v[4] = {r.km_x10, r.horas_x100, fuelOf(r.km_x10), tollCost(r)};
        for (int c = 0; c < 4; ++c) {
            vals[c].push_back(v[c]);
            s.top[c].push_back({r.id, r.origen, r.destino, static_cast<double>(v[c]) / static_cast<double>(scales[c])});
        }
        const string& d1 = st.cities.at(r.origen).departamento;
        const string& d2 = st.cities.at(r.destino).departamento;
        for (const auto& tid : r.peajes) {
            if (!st.tolls.at(tid).activo) continue;
            deptTolls[d1].insert(tid);
            deptTolls[d2].insert(tid);
        }
    }
    for (int c = 0; c < 4; ++c) {
        s.series[c] = makeSeries(vals[c], scales[c]);
        auto& t = s.top[c];
        std::stable_sort(t.begin(), t.end(), [](const TopRow& a, const TopRow& b) {
            return a.valor != b.valor ? a.valor > b.valor : a.id < b.id;
        });
        if (t.size() > 5) t.resize(5);
    }
    for (const auto& kv : deptTolls) {
        DeptRow d;
        d.departamento = kv.first;
        d.cantidad = static_cast<ll>(kv.second.size());
        for (const auto& tid : kv.second) d.tarifa_total += st.tolls.at(tid).tarifa;
        s.deptos.push_back(d);
    }
    std::stable_sort(s.deptos.begin(), s.deptos.end(), [](const DeptRow& a, const DeptRow& b) {
        return a.cantidad != b.cantidad ? a.cantidad > b.cantidad : a.departamento < b.departamento;
    });
    for (const auto& kv : st.cities) s.grados.push_back({kv.first, kv.second.nombre, degree(kv.first)});
    std::stable_sort(s.grados.begin(), s.grados.end(), [](const DegRow& a, const DegRow& b) {
        return a.grado != b.grado ? a.grado > b.grado : a.id < b.id;
    });
    std::set<string> seen;
    for (const auto& kv : st.cities) {
        if (!kv.second.activo || seen.count(kv.first)) continue;
        ++s.componentes;
        vector<string> stack{kv.first};
        seen.insert(kv.first);
        while (!stack.empty()) {
            string u = stack.back();
            stack.pop_back();
            for (const Edge& e : gDistancia.adj.at(u))
                if (seen.insert(e.to).second) stack.push_back(e.to);
        }
    }
    return s;
}

// ================================================================ 7. protocolo --api
struct Req {
    std::map<string, JV> m;
    const JV* get(const string& k) const {
        auto it = m.find(k);
        return (it == m.end() || it->second.kind == 'n') ? nullptr : &it->second;
    }
};

static bool badField(string& err, const string& k) {
    err = "Campo inválido: " + k;
    return false;
}
static bool fStr(const Req& r, const string& k, std::optional<string>& out, string& err) {
    const JV* v = r.get(k);
    if (!v) return true;
    if (v->kind == 's') out = v->s;
    else if (v->kind == 'i') out = std::to_string(v->i);
    else if (v->kind == 'd') out = v->s;
    else return badField(err, k);
    return true;
}
static bool fId(const Req& r, const string& k, std::optional<string>& out, string& err) {
    if (!fStr(r, k, out, err)) return false;
    if (out && (out->empty() || out->find_first_of(";|\r\n") != string::npos)) return badField(err, k);
    return true;
}
static bool fText(const Req& r, const string& k, std::optional<string>& out, string& err) {
    if (!fStr(r, k, out, err)) return false;
    return true;
}
static bool fScaled(const Req& r, const string& k, ll scale, ll lo, ll hi, std::optional<ll>& out, string& err) {
    const JV* v = r.get(k);
    if (!v) return true;
    double d = 0;
    if (v->kind == 'i' || v->kind == 'd') d = v->d;
    else if (v->kind == 's') {
        if (!parseDecimal(v->s, d)) return badField(err, k);
    } else {
        return badField(err, k);
    }
    ll o;
    if (!toScaled(d, scale, lo, hi, o)) return badField(err, k);
    out = o;
    return true;
}
static bool fBool(const Req& r, const string& k, std::optional<bool>& out, string& err) {
    const JV* v = r.get(k);
    if (!v) return true;
    if (v->kind == 'b' || (v->kind == 'i' && (v->i == 0 || v->i == 1))) out = v->i != 0;
    else if (v->kind == 's' && (v->s == "true" || v->s == "1")) out = true;
    else if (v->kind == 's' && (v->s == "false" || v->s == "0")) out = false;
    else return badField(err, k);
    return true;
}
static bool fList(const Req& r, const string& k, std::optional<vector<string>>& out, string& err) {
    const JV* v = r.get(k);
    if (!v) return true;
    if (v->kind != 's' && v->kind != 'a') return badField(err, k);
    vector<string> l;
    if (v->kind == 'a') l = v->list;
    else if (!v->s.empty()) l = splitBy(v->s, '|');
    for (const auto& x : l)
        if (x.empty() || x.find_first_of(";|\r\n") != string::npos) return badField(err, k);
    out = l;
    return true;
}
template <class T>
static bool need(const std::optional<T>& o, const string& k, string& err) {
    return o ? true : badField(err, k);
}

static string cityJson(const Pera& p, const City& c) {
    return "{\"id\":" + jstr(c.id) + ",\"nombre\":" + jstr(c.nombre) + ",\"departamento\":" + jstr(c.departamento) +
           ",\"lat\":" + jfloat(static_cast<double>(c.lat) / 1e5) + ",\"lon\":" + jfloat(static_cast<double>(c.lon) / 1e5) +
           ",\"activo\":" + jbool(c.activo) + ",\"grado\":" + std::to_string(p.degree(c.id)) + "}";
}
static string tollJson(const Toll& t) {
    return "{\"id\":" + jstr(t.id) + ",\"nombre\":" + jstr(t.nombre) + ",\"lat\":" + jfloat(static_cast<double>(t.lat) / 1e5) +
           ",\"lon\":" + jfloat(static_cast<double>(t.lon) / 1e5) + ",\"tarifa\":" + std::to_string(t.tarifa) +
           ",\"activo\":" + jbool(t.activo) + "}";
}
static string routeJson(const Pera& p, const Route& r) {
    string ids = "[";
    for (size_t i = 0; i < r.peajes.size(); ++i) ids += (i ? "," : "") + jstr(r.peajes[i]);
    ids += "]";
    return "{\"id\":" + jstr(r.id) + ",\"origen\":" + jstr(r.origen) + ",\"destino\":" + jstr(r.destino) +
           ",\"km\":" + jfloat(static_cast<double>(r.km_x10) / 10.0) + ",\"horas\":" + jfloat(static_cast<double>(r.horas_x100) / 100.0) +
           ",\"peajes\":" + ids + ",\"activo\":" + jbool(r.activo) + ",\"efectiva\":" + jbool(p.effective(r)) +
           ",\"combustible\":" + std::to_string(p.fuelOf(r.km_x10)) + ",\"peajes_costo\":" + std::to_string(p.tollCost(r)) + "}";
}
static string strArr(const vector<string>& v) {
    string o = "[";
    for (size_t i = 0; i < v.size(); ++i) o += (i ? "," : "") + jstr(v[i]);
    return o + "]";
}
static string paramsJson(const Params& p) {
    return "{\"consumo_km_gal\":" + jfloat(static_cast<double>(p.consumo_x10) / 10.0) +
           ",\"precio_gal\":" + std::to_string(p.precio) + ",\"velocidad_kmh\":" + std::to_string(p.velocidad) + "}";
}
static string queryJson(const string& from, const string& to, const QueryRes& q) {
    string o = "{\"from\":" + jstr(from) + ",\"to\":" + jstr(to) + ",\"alcanzable\":" + jbool(q.reachable);
    if (q.reachable) {
        o += ",\"criterios\":{";
        for (int c = 0; c < 5; ++c) {
            const PathRes& p = q.by[c];
            o += string(c ? "," : "") + "\"" + CRIT_Q[c] + "\":{\"ciudades\":" + strArr(p.cities) + ",\"rutas\":" +
                 strArr(p.routes) + ",\"totales\":{\"km\":" + jfloat(static_cast<double>(p.km_x10) / 10.0) +
                 ",\"horas\":" + jfloat(static_cast<double>(p.horas_x100) / 100.0) +
                 ",\"combustible\":" + std::to_string(p.combustible) + ",\"peajes\":" + std::to_string(p.peajes) + "}}";
        }
        o += "}";
    }
    return o + "}";
}
static string statsJson(const Stats& s) {
    string o = "{\"conteos\":{\"ciudades\":" + std::to_string(s.ciudades) + ",\"ciudades_activas\":" +
               std::to_string(s.ciudades_activas) + ",\"peajes\":" + std::to_string(s.peajes) +
               ",\"peajes_activos\":" + std::to_string(s.peajes_activos) + ",\"rutas\":" + std::to_string(s.rutas) +
               ",\"rutas_activas\":" + std::to_string(s.rutas_activas) + ",\"rutas_efectivas\":" +
               std::to_string(s.rutas_efectivas) + ",\"componentes\":" + std::to_string(s.componentes) + "},\"grafos\":{";
    for (int c = 0; c < 4; ++c) {
        const Series& x = s.series[c];
        auto sv = [&x](ll v) { return x.scale == 1 ? std::to_string(v) : jfloat(static_cast<double>(v) / static_cast<double>(x.scale)); };
        o += string(c ? "," : "") + "\"" + CRIT[c] + "\":{\"n\":" + std::to_string(x.n) + ",\"min\":" + sv(x.mn) +
             ",\"max\":" + sv(x.mx) + ",\"media\":" + jfloat(x.media) + ",\"mediana\":" + jfloat(x.mediana) +
             ",\"total\":" + sv(x.total) + ",\"hist\":{\"limites\":[";
        for (size_t i = 0; i < x.limites.size(); ++i) o += (i ? "," : "") + jfloat(x.limites[i]);
        o += "],\"cuentas\":[";
        for (size_t i = 0; i < x.cuentas.size(); ++i) o += (i ? "," : "") + std::to_string(x.cuentas[i]);
        o += "]}}";
    }
    o += "},\"peajes_por_departamento\":[";
    for (size_t i = 0; i < s.deptos.size(); ++i)
        o += string(i ? "," : "") + "{\"departamento\":" + jstr(s.deptos[i].departamento) + ",\"cantidad\":" +
             std::to_string(s.deptos[i].cantidad) + ",\"tarifa_total\":" + std::to_string(s.deptos[i].tarifa_total) + "}";
    o += "],\"grados\":[";
    for (size_t i = 0; i < s.grados.size(); ++i)
        o += string(i ? "," : "") + "{\"id\":" + jstr(s.grados[i].id) + ",\"nombre\":" + jstr(s.grados[i].nombre) +
             ",\"grado\":" + std::to_string(s.grados[i].grado) + "}";
    o += "],\"top_rutas\":{";
    for (int c = 0; c < 4; ++c) {
        o += string(c ? "," : "") + "\"" + CRIT[c] + "\":[";
        for (size_t i = 0; i < s.top[c].size(); ++i) {
            const TopRow& t = s.top[c][i];
            o += string(i ? "," : "") + "{\"id\":" + jstr(t.id) + ",\"origen\":" + jstr(t.origen) + ",\"destino\":" +
                 jstr(t.destino) + ",\"valor\":" + (c < 2 ? jfloat(t.valor) : std::to_string(static_cast<ll>(t.valor))) + "}";
        }
        o += "]";
    }
    return o + "}}";
}

class Engine {
public:
    Pera pera;
    bool stop = false;
    string dataPath = "data/pera_colombia.csv";

    string handle(const string& line) {
        Req req;
        string err;
        if (!JsonParser(line).parse(req.m, err)) return fail(err);
        const JV* av = req.get("action");
        const string a = (av && av->kind == 's') ? av->s : (av && av->kind == 'i') ? std::to_string(av->i) : string();
        string result = "{}";
        if (a == "ping") {
            result = "{\"backend\":\"cpp\",\"protocol\":\"1\"}";
        } else if (a == "state") {
        } else if (a == "reset") {
            pera.reset();
        } else if (a == "load" || a == "save") {
            string path = dataPath;
            const JV* p = req.get("path");
            if (p) {
                if (p->kind != 's') return fail("Campo inválido: path");
                path = p->s;
            }
            if (a == "load" ? !pera.load(path, err) : !pera.save(path, err)) return fail(err);
            result = "{\"path\":" + jstr(path) + ",\"ciudades\":" + std::to_string(pera.st.cities.size()) +
                     ",\"peajes\":" + std::to_string(pera.st.tolls.size()) + ",\"rutas\":" + std::to_string(pera.st.routes.size()) + "}";
        } else if (a == "undo") {
            if (!pera.undo(err)) return fail(err);
        } else if (a == "params") {
            result = paramsJson(pera.st.p);
        } else if (a == "set_params") {
            std::optional<ll> c, p, v;
            if (!fScaled(req, "consumo_km_gal", 10, 1, CONSUMO_MAX, c, err) ||
                !fScaled(req, "precio_gal", 1, 0, DINERO_MAX, p, err) ||
                !fScaled(req, "velocidad_kmh", 1, 1, VEL_MAX, v, err))
                return fail(err);
            pera.setParams(c, p, v);
            result = paramsJson(pera.st.p);
        } else if (a == "query") {
            std::optional<string> from, to;
            if (!fId(req, "from", from, err) || !fId(req, "to", to, err) || !need(from, "from", err) || !need(to, "to", err))
                return fail(err);
            QueryRes q;
            if (!pera.query(*from, *to, q, err)) return fail(err);
            if (*from == *to) {  // origen = destino: camino [id], totales 0
                q.reachable = true;
                for (auto& pr : q.by) pr.cities = {*from};
            }
            result = queryJson(*from, *to, q);
        } else if (a == "stats") {
            result = statsJson(pera.stats());
        } else if (a == "shutdown") {
            stop = true;
        } else if (a == "list" || a == "get" || a == "create" || a == "update" || a == "delete" || a == "toggle") {
            if (!entity(a, req, result, err)) return fail(err);
        } else {
            return fail("Acción desconocida: " + a);
        }
        return ok(result);
    }

private:
    string stateJson() const {
        return "{\"dirty\":" + jbool(pera.dirty) + ",\"ciudades\":" + std::to_string(pera.st.cities.size()) +
               ",\"peajes\":" + std::to_string(pera.st.tolls.size()) + ",\"rutas\":" + std::to_string(pera.st.routes.size()) + "}";
    }
    string fail(const string& m) const { return "{\"ok\":false,\"error\":" + jstr(m) + ",\"state\":" + stateJson() + "}"; }
    string ok(const string& result) const { return "{\"ok\":true,\"result\":" + result + ",\"state\":" + stateJson() + "}"; }

    bool entity(const string& a, const Req& req, string& result, string& err) {
        std::optional<string> kind, id;
        if (!fStr(req, "kind", kind, err) || !need(kind, "kind", err)) return false;
        const string k = *kind;
        if (k != "city" && k != "toll" && k != "route") return badField(err, "kind");
        if (!fId(req, "id", id, err)) return false;
        const Pera& P = pera;
        auto item = [&](const string& i) -> string {
            if (k == "city") return cityJson(P, P.st.cities.at(i));
            if (k == "toll") return tollJson(P.st.tolls.at(i));
            return routeJson(P, P.st.routes.at(i));
        };
        auto missing = [&](const string& i) {
            err = string(k == "city" ? "La ciudad " : k == "toll" ? "El peaje " : "La ruta ") + i + " no existe";
            return false;
        };
        auto exists = [&](const string& i) {
            return k == "city" ? P.st.cities.count(i) : k == "toll" ? P.st.tolls.count(i) : P.st.routes.count(i);
        };
        if (a == "list") {
            string o = "{\"items\":[";
            bool first = true;
            auto sep = [&] { string s = first ? "" : ","; first = false; return s; };
            if (k == "city") for (const auto& kv : P.st.cities) o += sep() + cityJson(P, kv.second);
            else if (k == "toll") for (const auto& kv : P.st.tolls) o += sep() + tollJson(kv.second);
            else for (const auto& kv : P.st.routes) o += sep() + routeJson(P, kv.second);
            result = o + "]}";
            return true;
        }
        if (a == "create") return create(k, req, id, result, err);
        if (!need(id, "id", err)) return false;
        if (!exists(*id)) return missing(*id);
        if (a == "get") {
            result = item(*id);
        } else if (a == "update") {
            if (!update(k, req, *id, err)) return false;
            result = item(*id);
        } else if (a == "toggle") {
            bool good = k == "city" ? pera.toggleCity(*id, err) : k == "toll" ? pera.toggleToll(*id, err) : pera.toggleRoute(*id, err);
            if (!good) return false;
            result = item(*id);
        } else {  // delete
            if (k == "city") {
                vector<string> removed;
                if (!pera.deleteCity(*id, removed, err)) return false;
                result = "{\"id\":" + jstr(*id) + ",\"rutas_eliminadas\":" + strArr(removed) + "}";
            } else {
                if (!(k == "toll" ? pera.deleteToll(*id, err) : pera.deleteRoute(*id, err))) return false;
                result = "{\"id\":" + jstr(*id) + "}";
            }
        }
        return true;
    }

    bool create(const string& k, const Req& req, const std::optional<string>& id, string& result, string& err) {
        std::optional<string> nombre, depto, origen, destino;
        std::optional<ll> lat, lon, tarifa, km, horas;
        std::optional<bool> activo;
        std::optional<vector<string>> peajes;
        if (id) {
            bool dup = k == "city" ? pera.st.cities.count(*id) : k == "toll" ? pera.st.tolls.count(*id) : pera.st.routes.count(*id);
            if (dup) {
                err = string(k == "city" ? "La ciudad " : k == "toll" ? "El peaje " : "La ruta ") + *id + " ya existe";
                return false;
            }
        }
        if (k == "city") {
            if (!need(id, "id", err)) return false;
            if (!fText(req, "nombre", nombre, err) || !fText(req, "departamento", depto, err) ||
                !fScaled(req, "lat", 100000, -LAT_MAX, LAT_MAX, lat, err) ||
                !fScaled(req, "lon", 100000, -LON_MAX, LON_MAX, lon, err) || !fBool(req, "activo", activo, err))
                return false;
            if (!need(id, "id", err) || !need(nombre, "nombre", err) || !need(depto, "departamento", err) ||
                !need(lat, "lat", err) || !need(lon, "lon", err))
                return false;
            City c;
            c.id = *id; c.nombre = *nombre; c.departamento = *depto; c.lat = *lat; c.lon = *lon;
            c.activo = activo.value_or(true);
            if (!pera.createCity(c, err)) return false;
            result = cityJson(pera, pera.st.cities.at(c.id));
        } else if (k == "toll") {
            if (!fText(req, "nombre", nombre, err) || !fScaled(req, "lat", 100000, -LAT_MAX, LAT_MAX, lat, err) ||
                !fScaled(req, "lon", 100000, -LON_MAX, LON_MAX, lon, err) ||
                !fScaled(req, "tarifa", 1, 0, DINERO_MAX, tarifa, err) || !fBool(req, "activo", activo, err))
                return false;
            if (!need(nombre, "nombre", err) || !need(lat, "lat", err) || !need(lon, "lon", err) || !need(tarifa, "tarifa", err))
                return false;
            Toll t;
            t.id = id.value_or(""); t.nombre = *nombre; t.lat = *lat; t.lon = *lon; t.tarifa = *tarifa;
            t.activo = activo.value_or(true);
            if (!pera.createToll(t, err)) return false;
            result = tollJson(pera.st.tolls.at(t.id.empty() ? lastId(false) : t.id));
        } else {
            if (!fId(req, "origen", origen, err) || !fId(req, "destino", destino, err) ||
                !fScaled(req, "km", 10, 1, KM_MAX, km, err) || !fScaled(req, "horas", 100, 1, HORAS_MAX, horas, err) ||
                !fList(req, "peajes", peajes, err) || !fBool(req, "activo", activo, err))
                return false;
            if (!need(origen, "origen", err) || !need(destino, "destino", err) || !need(km, "km", err) || !need(horas, "horas", err))
                return false;
            Route r;
            r.id = id.value_or(""); r.origen = *origen; r.destino = *destino; r.km_x10 = *km; r.horas_x100 = *horas;
            r.peajes = peajes.value_or(vector<string>());
            r.activo = activo.value_or(true);
            if (!pera.createRoute(r, err)) return false;
            // el id asignado es el último creado
            string rid = r.id.empty() ? lastId(true) : r.id;
            result = routeJson(pera, pera.st.routes.at(rid));
        }
        return true;
    }
    // id asignado automáticamente: el mayor P### / R### numérico
    string lastId(bool route) const {
        string best;
        ll mx = -1;
        auto scan = [&](const string& i) {
            if (i.size() < 2 || i[0] != (route ? 'R' : 'P') || i.size() > 16) return;
            for (size_t j = 1; j < i.size(); ++j)
                if (i[j] < '0' || i[j] > '9') return;
            if (std::stoll(i.substr(1)) > mx) { mx = std::stoll(i.substr(1)); best = i; }
        };
        if (route) for (const auto& kv : pera.st.routes) scan(kv.first);
        else for (const auto& kv : pera.st.tolls) scan(kv.first);
        return best;
    }

    bool update(const string& k, const Req& req, const string& id, string& err) {
        std::optional<string> nombre, depto, origen, destino;
        std::optional<ll> lat, lon, tarifa, km, horas;
        std::optional<bool> activo;
        std::optional<vector<string>> peajes;
        if (k == "city") {
            if (!fText(req, "nombre", nombre, err) || !fText(req, "departamento", depto, err) ||
                !fScaled(req, "lat", 100000, -LAT_MAX, LAT_MAX, lat, err) ||
                !fScaled(req, "lon", 100000, -LON_MAX, LON_MAX, lon, err) || !fBool(req, "activo", activo, err))
                return false;
            CityPatch p;
            p.nombre = nombre; p.departamento = depto; p.lat = lat; p.lon = lon; p.activo = activo;
            return pera.updateCity(id, p, err);
        }
        if (k == "toll") {
            if (!fText(req, "nombre", nombre, err) || !fScaled(req, "lat", 100000, -LAT_MAX, LAT_MAX, lat, err) ||
                !fScaled(req, "lon", 100000, -LON_MAX, LON_MAX, lon, err) ||
                !fScaled(req, "tarifa", 1, 0, DINERO_MAX, tarifa, err) || !fBool(req, "activo", activo, err))
                return false;
            TollPatch p;
            p.nombre = nombre; p.lat = lat; p.lon = lon; p.tarifa = tarifa; p.activo = activo;
            return pera.updateToll(id, p, err);
        }
        if (!fId(req, "origen", origen, err) || !fId(req, "destino", destino, err) ||
            !fScaled(req, "km", 10, 1, KM_MAX, km, err) || !fScaled(req, "horas", 100, 1, HORAS_MAX, horas, err) ||
            !fList(req, "peajes", peajes, err) || !fBool(req, "activo", activo, err))
            return false;
        RoutePatch p;
        p.origen = origen; p.destino = destino; p.km_x10 = km; p.horas_x100 = horas; p.peajes = peajes; p.activo = activo;
        return pera.updateRoute(id, p, err);
    }
};

// ================================================================ 8. autoprueba
static int g_fails = 0;
#define CHECK(c)                                                     \
    do {                                                             \
        if (!(c)) {                                                  \
            ++g_fails;                                               \
            std::cerr << "FALLO línea " << __LINE__ << ": " #c "\n"; \
        }                                                            \
    } while (0)

static const char* MINI =
    "# PERA v1\nK;consumo_km_gal;40.0\nK;precio_gal;16000\nK;velocidad_kmh;55\n"
    "C;11001;Bogotá D.C.;Bogotá D.C.;4.71100;-74.07210;1\nC;15001;Tunja;Boyacá;5.53530;-73.36780;1\n"
    "C;50001;Villavicencio;Meta;4.14200;-73.62660;1\nC;73001;Ibagué;Tolima;4.43890;-75.23220;1\n"
    "C;91001;Leticia;Amazonas;-4.21530;-69.94060;1\n"
    "P;P001;Peaje Tunja;5.12000;-73.80000;12900;1\nP;P002;Peaje Chusacá;4.45000;-74.20000;11800;1\n"
    "P;P003;Peaje Cajamarca;4.44000;-75.42000;13400;1\nP;P004;Peaje Naranjal;4.35000;-73.70000;20000;1\n"
    "P;P005;Peaje Inactivo;4.40000;-74.60000;9000;0\n"
    "R;R001;11001;15001;147.0;2.75;P001;1\nR;R002;11001;73001;195.0;3.60;P002|P003|P005;1\n"
    "R;R003;11001;50001;86.0;2.20;P004;1\nR;R004;15001;50001;230.0;5.50;;1\n"
    "R;R005;73001;50001;350.0;7.00;;1\nR;R006;15001;73001;300.0;6.00;;0\n";

static bool loadText(Pera& p, const string& text, string& err) {
    std::istringstream in(text);
    State s;
    if (!Pera::parseState(in, s, err)) return false;
    p.st = std::move(s);
    p.dirty = false;
    p.history.clear();
    p.rebuild();
    return true;
}

static Pera miniPera() {
    Pera p;
    string e;
    if (!loadText(p, MINI, e)) std::cerr << "mini no carga: " << e << "\n";
    return p;
}

static void expectPath(const PathRes& p, const vector<string>& cities, const vector<string>& routes, ll km, ll horas,
                       ll comb, ll peajes) {
    CHECK(p.cities == cities);
    CHECK(p.routes == routes);
    CHECK(p.km_x10 == km);
    CHECK(p.horas_x100 == horas);
    CHECK(p.combustible == comb);
    CHECK(p.peajes == peajes);
}

static void testQueries() {
    Pera p = miniPera();
    CHECK(p.serialize() == MINI);  // cargar y guardar reproduce el archivo
    CHECK(p.st.cities.size() == 5 && p.st.tolls.size() == 5 && p.st.routes.size() == 6);
    QueryRes q;
    string e;
    CHECK(p.query("11001", "50001", q, e) && q.reachable);
    expectPath(q.by[0], {"11001", "50001"}, {"R003"}, 860, 220, 34400, 20000);
    expectPath(q.by[1], {"11001", "50001"}, {"R003"}, 860, 220, 34400, 20000);
    expectPath(q.by[2], {"11001", "50001"}, {"R003"}, 860, 220, 34400, 20000);
    expectPath(q.by[3], {"11001", "15001", "50001"}, {"R001", "R004"}, 3770, 825, 150800, 12900);
    CHECK(p.query("11001", "91001", q, e) && !q.reachable);  // Leticia es isla
    CHECK(p.query("11001", "11001", q, e));
    CHECK(!p.query("11001", "99999", q, e) && e == "La ciudad 99999 no existe");
    // R002 incluye P005 inactivo: no suma
    CHECK(p.tollCost(p.st.routes.at("R002")) == 25200);
    CHECK(!p.effective(p.st.routes.at("R006")));
    CHECK(p.fuelOf(860) == 34400);
    // ruta inactiva R006 no participa: Tunja->Ibagué pasa por Bogotá
    CHECK(p.query("15001", "73001", q, e));
    CHECK(q.by[0].routes == (vector<string>{"R001", "R002"}));
    // ciudad inactiva: no se puede consultar y corta el camino
    CHECK(p.toggleCity("15001", e));
    CHECK(!p.query("15001", "50001", q, e) && e == "Ciudad inactiva: 15001");
    CHECK(p.query("11001", "50001", q, e) && q.by[3].routes == (vector<string>{"R003"}));
    CHECK(p.undo(e));
    CHECK(p.st.cities.at("15001").activo);
    // parámetros: precio del galón cambia el combustible
    p.setParams(std::nullopt, 20000, std::nullopt);
    CHECK(p.query("11001", "50001", q, e) && q.by[0].combustible == 43000);
    CHECK(p.undo(e) && p.st.p.precio == 16000);
}

static void testIntegrity() {
    Pera p = miniPera();
    string e;
    Route r;
    r.id = "R007"; r.origen = "50001"; r.destino = "11001"; r.km_x10 = 10; r.horas_x100 = 10;
    CHECK(!p.createRoute(r, e) && e == "La ruta entre 50001 y 11001 ya existe");
    r.origen = r.destino = "11001";
    CHECK(!p.createRoute(r, e) && e == "Una ruta necesita dos ciudades distintas");
    r.origen = "11001"; r.destino = "00000";
    CHECK(!p.createRoute(r, e) && e == "La ciudad 00000 no existe");
    r.destino = "91001"; r.peajes = {"P404"};
    CHECK(!p.createRoute(r, e) && e == "El peaje P404 no existe");
    r.peajes.clear(); r.id = "";
    CHECK(p.createRoute(r, e) && p.st.routes.count("R007"));  // id automático R007
    City c;
    c.id = "11001";
    CHECK(!p.createCity(c, e) && e == "La ciudad 11001 ya existe");
    Toll t;
    t.nombre = "Nuevo";
    CHECK(p.createToll(t, e) && p.st.tolls.count("P006"));
    // eliminar un peaje lo quita de las rutas
    CHECK(p.deleteToll("P003", e));
    CHECK(p.st.routes.at("R002").peajes == (vector<string>{"P002", "P005"}));
    // eliminar ciudad elimina sus rutas
    vector<string> removed;
    CHECK(p.deleteCity("11001", removed, e));
    CHECK(removed == (vector<string>{"R001", "R002", "R003", "R007"}));
    CHECK(p.st.routes.size() == 3 && !p.st.cities.count("11001"));
    CHECK(p.degree("50001") == 2);
    CHECK(p.undo(e) && p.st.cities.count("11001") && p.st.routes.size() == 7);
    // deshacer hasta vaciar la historia
    int n = 0;
    while (p.undo(e)) ++n;
    CHECK(n >= 3 && e == "No hay nada que deshacer");
    CHECK(p.serialize() == MINI);
}

static void testFiles() {
    auto dir = std::filesystem::temp_directory_path() / "pera_selftest";
    std::filesystem::create_directories(dir);
    string f = (dir / "sub" / "a.csv").string(), e;
    Pera p = miniPera();
    CHECK(p.save(f, e));
    std::ifstream in(f, std::ios::binary);
    std::stringstream ss;
    ss << in.rdbuf();
    CHECK(ss.str() == MINI);
    Pera q;
    CHECK(q.load(f, e) && q.serialize() == MINI);
    // errores de carga: atómicos
    const char* bads[] = {"basura\n",
                          "C;1;a;b;4.0;-74.0;1\nC;1;a;b;4.0;-74.0;1\n",
                          "C;1;a;b;4.0;-74.0;1\nR;R1;1;2;1.0;1.00;;1\n",
                          "C;1;a;b;4.0;-74.0;1\nC;2;a;b;4.0;-74.0;1\nR;R1;1;1;1.0;1.00;;1\n",
                          "C;1;a;b;4.0;-74.0;1\nC;2;a;b;4.0;-74.0;1\nR;R1;1;2;1.0;1.00;;1\nR;R2;2;1;1.0;1.00;;1\n",
                          "C;1;a;b;4.0;-74.0;1\nC;2;a;b;4.0;-74.0;1\nR;R1;1;2;1.0;1.00;P9;1\n",
                          "C;1;a;b;99.0;-74.0;1\n",
                          "C;1;a;b;4.0;-74.0;7\n",
                          "K;precio_gal;abc\n"};
    for (const char* b : bads) {
        Pera r = miniPera();
        string err;
        CHECK(!loadText(r, b, err) && err.rfind("Archivo inválido", 0) == 0);
        std::ofstream(dir / "bad.csv", std::ios::binary) << b;
        CHECK(!r.load((dir / "bad.csv").string(), err));
        CHECK(r.serialize() == MINI);
    }
    CHECK(!q.load((dir / "no_existe.csv").string(), e));
    CHECK(q.serialize() == MINI);
    // archivo vacío es válido
    Pera v = miniPera();
    string err;
    CHECK(loadText(v, "# PERA v1\n\n", err) && v.st.cities.empty());
    // nombres con ';' se sustituyen
    City c;
    c.id = "1"; c.nombre = sanitize("a;b"); c.departamento = "d";
    CHECK(c.nombre == "a b");
    std::filesystem::remove_all(dir);
}

static void testStats() {
    Pera p = miniPera();
    Stats s = p.stats();
    CHECK(s.ciudades == 5 && s.peajes == 5 && s.rutas == 6 && s.rutas_activas == 5 && s.rutas_efectivas == 5);
    CHECK(s.peajes_activos == 4 && s.componentes == 2);
    CHECK(s.series[0].n == 5 && s.series[0].mn == 860 && s.series[0].mx == 3500 && s.series[0].total == 10080);
    CHECK(std::fabs(s.series[0].mediana - 195.0) < 1e-9);
    CHECK(s.series[0].cuentas.size() == 10 && s.series[0].cuentas[0] + s.series[0].cuentas[9] >= 2);
    ll sum = 0;
    for (ll c : s.series[1].cuentas) sum += c;
    CHECK(sum == 5);
    CHECK(s.grados[0].id == "11001" && s.grados[0].grado == 3 && s.grados.back().id == "91001");
    CHECK(s.top[0][0].id == "R005" && s.top[0].size() == 5);
    // peajes por departamento: P001 en Bogotá y Boyacá, P002/P003 en Bogotá y Tolima, P004 en Bogotá y Meta
    CHECK(!s.deptos.empty() && s.deptos[0].departamento == "Bogotá D.C." && s.deptos[0].cantidad == 4);
    Pera e;
    Stats z = e.stats();
    CHECK(z.rutas_efectivas == 0 && z.componentes == 0 && z.series[0].n == 0 && z.series[0].limites.size() == 11);
}

static void testProtocol() {
    Engine g;
    string e;
    auto has = [](const string& s, const string& frag) { return s.find(frag) != string::npos; };
    CHECK(has(g.handle("{\"action\":\"ping\"}"), "\"backend\":\"cpp\""));
    auto path = (std::filesystem::temp_directory_path() / "pera_selftest_mini.csv");
    { std::ofstream(path, std::ios::binary) << MINI; }
    string r = g.handle("{\"action\":\"load\",\"path\":" + jstr(path.string()) + "}");
    CHECK(has(r, "\"ok\":true") && has(r, "\"ciudades\":5,\"peajes\":5,\"rutas\":6}}"));
    r = g.handle("{\"action\":\"query\",\"from\":\"11001\",\"to\":\"50001\"}");
    CHECK(has(r, "\"peajes\":{\"ciudades\":[\"11001\",\"15001\",\"50001\"],\"rutas\":[\"R001\",\"R004\"]"));
    CHECK(has(r, "\"combustible\":150800,\"peajes\":12900"));
    r = g.handle("{\"action\":\"query\",\"from\":\"11001\",\"to\":\"91001\"}");
    CHECK(has(r, "\"alcanzable\":false}"));
    r = g.handle("{\"action\":\"create\",\"kind\":\"route\",\"origen\":\"50001\",\"destino\":\"11001\",\"km\":10,\"horas\":1}");
    CHECK(has(r, "\"ok\":false") && has(r, "La ruta entre 50001 y 11001 ya existe"));
    r = g.handle("{\"action\":\"create\",\"kind\":\"toll\",\"nombre\":\"X\",\"lat\":1.5,\"lon\":-70,\"tarifa\":\"9000\"}");
    CHECK(has(r, "\"id\":\"P006\"") && has(r, "\"dirty\":true"));
    r = g.handle("{\"action\":\"delete\",\"kind\":\"city\",\"id\":\"11001\"}");
    CHECK(has(r, "\"rutas_eliminadas\":[\"R001\",\"R002\",\"R003\"]"));
    r = g.handle("{\"action\":\"undo\"}");
    CHECK(has(r, "\"ciudades\":5"));
    CHECK(has(g.handle("{\"action\":\"nada\"}"), "Acción desconocida: nada"));
    CHECK(has(g.handle("{\"action\":\"get\",\"kind\":\"city\",\"id\":\"1\"}"), "La ciudad 1 no existe"));
    CHECK(has(g.handle("{\"action\":\"update\",\"kind\":\"city\",\"id\":\"11001\",\"lat\":\"x\"}"), "Campo inválido: lat"));
    CHECK(has(g.handle("{no json"), "\"ok\":false"));
    std::filesystem::remove(path);
}

static int selfTest() {
    testQueries();
    testIntegrity();
    testFiles();
    testStats();
    testProtocol();
    if (g_fails) {
        std::cout << "FALLO (" << g_fails << ")\n";
        return 1;
    }
    std::cout << "OK\n";
    return 0;
}

// ================================================================ 9. consola
struct Eof {};

static const char* RESET = "\x1b[0m";
static const char* BOLD = "\x1b[1m";
static const char* DIM = "\x1b[90m";
static const char* CYAN = "\x1b[36m";
static const char* GREEN = "\x1b[32m";
static const char* RED = "\x1b[31m";

static string ask(const string& prompt) {
    std::cout << prompt << std::flush;
    string s;
    if (!std::getline(std::cin, s)) throw Eof();
    while (!s.empty() && (s.back() == '\r' || s.back() == ' ')) s.pop_back();
    size_t i = 0;
    while (i < s.size() && s[i] == ' ') ++i;
    return s.substr(i);
}
static bool yes(const string& s) { return !s.empty() && (s[0] == 's' || s[0] == 'S' || s[0] == 'y' || s[0] == 'Y'); }

static size_t ulen(const string& s) {
    size_t n = 0;
    for (unsigned char c : s) n += (c & 0xC0) != 0x80;
    return n;
}
static string padR(const string& s, size_t w) { return s + string(w > ulen(s) ? w - ulen(s) : 0, ' '); }
static string padL(const string& s, size_t w) { return string(w > ulen(s) ? w - ulen(s) : 0, ' ') + s; }
static string cut(const string& s, size_t w) {
    if (ulen(s) <= w) return s;
    size_t n = 0, i = 0;
    for (; i < s.size(); ++i) {
        if ((static_cast<unsigned char>(s[i]) & 0xC0) != 0x80 && n++ == w - 1) break;
    }
    return s.substr(0, i) + "…";
}

static string cop(ll v) {
    string d = std::to_string(v < 0 ? -v : v), o;
    for (size_t i = 0; i < d.size(); ++i) {
        if (i && (d.size() - i) % 3 == 0) o += '.';
        o += d[i];
    }
    return "$" + string(v < 0 ? "-" : "") + o;
}
static string kmTxt(ll x10) { return fixedScaled(x10, 1) + " km"; }
static string hrTxt(ll x100) {
    ll min = (x100 * 60 + 50) / 100;
    return std::to_string(min / 60) + " h " + std::to_string(min % 60) + " min";
}
static string num2(double v, int dec) {
    char b[40];
    std::snprintf(b, sizeof b, "%.*f", dec, v);
    return b;
}

static string cityLabel(const Pera& p, const string& id) {
    auto it = p.st.cities.find(id);
    return it == p.st.cities.end() ? id : it->second.nombre + " (" + id + ")";
}

static void listCities(const Pera& p) {
    std::cout << BOLD << padR("ID", 8) << padR("Nombre", 24) << padR("Departamento", 22) << padL("Lat", 10)
              << padL("Lon", 11) << padL("Grado", 7) << "  Estado" << RESET << "\n";
    for (const auto& kv : p.st.cities) {
        const City& c = kv.second;
        std::cout << padR(c.id, 8) << padR(cut(c.nombre, 23), 24) << padR(cut(c.departamento, 21), 22)
                  << padL(fixedScaled(c.lat, 5), 10) << padL(fixedScaled(c.lon, 5), 11) << padL(std::to_string(p.degree(c.id)), 7)
                  << "  " << (c.activo ? string(GREEN) + "activa" : string(DIM) + "inactiva") << RESET << "\n";
    }
    if (p.st.cities.empty()) std::cout << "(sin ciudades)\n";
}
static void listTolls(const Pera& p) {
    std::cout << BOLD << padR("ID", 7) << padR("Nombre", 28) << padL("Lat", 10) << padL("Lon", 11) << padL("Tarifa", 11)
              << "  Estado" << RESET << "\n";
    for (const auto& kv : p.st.tolls) {
        const Toll& t = kv.second;
        std::cout << padR(t.id, 7) << padR(cut(t.nombre, 27), 28) << padL(fixedScaled(t.lat, 5), 10)
                  << padL(fixedScaled(t.lon, 5), 11) << padL(cop(t.tarifa), 11) << "  "
                  << (t.activo ? string(GREEN) + "activo" : string(DIM) + "inactivo") << RESET << "\n";
    }
    if (p.st.tolls.empty()) std::cout << "(sin peajes)\n";
}
static void listRoutes(const Pera& p) {
    std::cout << BOLD << padR("ID", 7) << padR("Origen", 17) << padR("Destino", 17) << padL("Km", 8) << padL("Horas", 7)
              << padL("Combustible", 13) << padL("Peajes", 10) << "  Estado  Lista" << RESET << "\n";
    for (const auto& kv : p.st.routes) {
        const Route& r = kv.second;
        auto nm = [&](const string& id) {
            auto it = p.st.cities.find(id);
            return it == p.st.cities.end() ? id : it->second.nombre;
        };
        string estado = !r.activo ? string(DIM) + "inactiva" : p.effective(r) ? string(GREEN) + "efectiva" : string(RED) + "sin ciudad";
        std::cout << padR(r.id, 7) << padR(cut(nm(r.origen), 16), 17) << padR(cut(nm(r.destino), 16), 17)
                  << padL(fixedScaled(r.km_x10, 1), 8) << padL(fixedScaled(r.horas_x100, 2), 7)
                  << padL(cop(p.fuelOf(r.km_x10)), 13) << padL(cop(p.tollCost(r)), 10) << "  " << estado << RESET << "  "
                  << joinBy(r.peajes, '|') << "\n";
    }
    if (p.st.routes.empty()) std::cout << "(sin rutas)\n";
}

// Pide un número escalado; vacío = conservar (si keep) o error.
static bool askScaled(const string& label, ll scale, ll lo, ll hi, std::optional<ll>& out, bool keep) {
    string s = ask(label + (keep ? " (Enter = sin cambio): " : ": "));
    if (s.empty() && keep) return true;
    double d;
    ll v;
    if (!parseDecimal(s, d) || !toScaled(d, scale, lo, hi, v)) {
        std::cout << RED << "Valor inválido para " << label << "." << RESET << "\n";
        return false;
    }
    out = v;
    return true;
}
static std::optional<string> askText(const string& label, bool keep) {
    string s = sanitize(ask(label + (keep ? " (Enter = sin cambio): " : ": ")));
    if (s.empty()) return std::nullopt;
    return s;
}

static void menuCities(Pera& p) {
    while (true) {
        std::cout << "\n" << BOLD << "CIUDADES" << RESET << "  1) Listar  2) Crear  3) Modificar  4) Eliminar  5) Desactivar/reactivar  0) Volver\n";
        string o = ask("Opción: "), e, id;
        if (o == "0") return;
        if (o == "1") { listCities(p); continue; }
        if (o == "2") {
            City c;
            c.id = ask("Id (código DANE): ");
            auto n = askText("Nombre", false), d = askText("Departamento", false);
            std::optional<ll> lat, lon;
            if (c.id.empty() || c.id.find_first_of(";|") != string::npos || !n || !d ||
                !askScaled("Latitud", 100000, -LAT_MAX, LAT_MAX, lat, false) ||
                !askScaled("Longitud", 100000, -LON_MAX, LON_MAX, lon, false)) {
                std::cout << RED << "Datos incompletos o inválidos." << RESET << "\n";
                continue;
            }
            c.nombre = *n; c.departamento = *d; c.lat = *lat; c.lon = *lon;
            std::cout << (p.createCity(c, e) ? string(GREEN) + "Ciudad creada." : string(RED) + e) << RESET << "\n";
            continue;
        }
        id = ask("Id de la ciudad: ");
        if (o == "3") {
            if (!p.st.cities.count(id)) { std::cout << RED << "La ciudad " << id << " no existe" << RESET << "\n"; continue; }
            CityPatch pt;
            pt.nombre = askText("Nombre", true);
            pt.departamento = askText("Departamento", true);
            if (!askScaled("Latitud", 100000, -LAT_MAX, LAT_MAX, pt.lat, true) ||
                !askScaled("Longitud", 100000, -LON_MAX, LON_MAX, pt.lon, true))
                continue;
            std::cout << (p.updateCity(id, pt, e) ? string(GREEN) + "Ciudad modificada." : string(RED) + e) << RESET << "\n";
        } else if (o == "4") {
            vector<string> rem;
            if (!p.deleteCity(id, rem, e)) std::cout << RED << e << RESET << "\n";
            else std::cout << GREEN << "Ciudad eliminada junto con " << rem.size() << " ruta(s)." << RESET << "\n";
        } else if (o == "5") {
            if (!p.toggleCity(id, e)) std::cout << RED << e << RESET << "\n";
            else std::cout << GREEN << "Ciudad " << (p.st.cities.at(id).activo ? "reactivada." : "desactivada.") << RESET << "\n";
        } else {
            std::cout << "Opción no válida.\n";
        }
    }
}

static void menuTolls(Pera& p) {
    while (true) {
        std::cout << "\n" << BOLD << "PEAJES" << RESET << "  1) Listar  2) Crear  3) Modificar  4) Eliminar  5) Desactivar/reactivar  0) Volver\n";
        string o = ask("Opción: "), e, id;
        if (o == "0") return;
        if (o == "1") { listTolls(p); continue; }
        if (o == "2") {
            auto n = askText("Nombre", false);
            std::optional<ll> lat, lon, tar;
            if (!n || !askScaled("Latitud", 100000, -LAT_MAX, LAT_MAX, lat, false) ||
                !askScaled("Longitud", 100000, -LON_MAX, LON_MAX, lon, false) ||
                !askScaled("Tarifa (COP, categoría I)", 1, 0, DINERO_MAX, tar, false)) {
                std::cout << RED << "Datos incompletos o inválidos." << RESET << "\n";
                continue;
            }
            Toll t;
            t.nombre = *n; t.lat = *lat; t.lon = *lon; t.tarifa = *tar;
            if (p.createToll(t, e)) std::cout << GREEN << "Peaje creado." << RESET << "\n";
            else std::cout << RED << e << RESET << "\n";
            continue;
        }
        id = ask("Id del peaje: ");
        if (o == "3") {
            if (!p.st.tolls.count(id)) { std::cout << RED << "El peaje " << id << " no existe" << RESET << "\n"; continue; }
            TollPatch pt;
            pt.nombre = askText("Nombre", true);
            if (!askScaled("Latitud", 100000, -LAT_MAX, LAT_MAX, pt.lat, true) ||
                !askScaled("Longitud", 100000, -LON_MAX, LON_MAX, pt.lon, true) ||
                !askScaled("Tarifa (COP)", 1, 0, DINERO_MAX, pt.tarifa, true))
                continue;
            std::cout << (p.updateToll(id, pt, e) ? string(GREEN) + "Peaje modificado." : string(RED) + e) << RESET << "\n";
        } else if (o == "4") {
            std::cout << (p.deleteToll(id, e) ? string(GREEN) + "Peaje eliminado (y quitado de las rutas)." : string(RED) + e) << RESET << "\n";
        } else if (o == "5") {
            if (!p.toggleToll(id, e)) std::cout << RED << e << RESET << "\n";
            else std::cout << GREEN << "Peaje " << (p.st.tolls.at(id).activo ? "reactivado." : "desactivado.") << RESET << "\n";
        } else {
            std::cout << "Opción no válida.\n";
        }
    }
}

static bool askPeajes(std::optional<vector<string>>& out) {
    string s = ask("Peajes (ids separados por |, '-' = ninguno, Enter = sin cambio): ");
    if (s.empty()) return true;
    vector<string> l;
    if (s != "-") {
        l = splitBy(s, '|');
        for (const auto& x : l)
            if (x.empty()) { std::cout << RED << "Lista de peajes mal formada." << RESET << "\n"; return false; }
    }
    out = l;
    return true;
}

static void menuRoutes(Pera& p) {
    while (true) {
        std::cout << "\n" << BOLD << "RUTAS" << RESET << "  1) Listar  2) Crear  3) Modificar  4) Eliminar  5) Desactivar/reactivar  0) Volver\n";
        string o = ask("Opción: "), e, id;
        if (o == "0") return;
        if (o == "1") { listRoutes(p); continue; }
        if (o == "2") {
            Route r;
            r.origen = ask("Id ciudad origen: ");
            r.destino = ask("Id ciudad destino: ");
            std::optional<ll> km, h;
            std::optional<vector<string>> pj;
            if (!askScaled("Distancia (km)", 10, 1, KM_MAX, km, false) || !askScaled("Tiempo (horas)", 100, 1, HORAS_MAX, h, false) ||
                !askPeajes(pj))
                continue;
            r.km_x10 = *km; r.horas_x100 = *h; r.peajes = pj.value_or(vector<string>());
            if (p.createRoute(r, e)) std::cout << GREEN << "Ruta creada." << RESET << "\n";
            else std::cout << RED << e << RESET << "\n";
            continue;
        }
        id = ask("Id de la ruta: ");
        if (o == "3") {
            if (!p.st.routes.count(id)) { std::cout << RED << "La ruta " << id << " no existe" << RESET << "\n"; continue; }
            RoutePatch pt;
            string a = ask("Origen (Enter = sin cambio): "), b = ask("Destino (Enter = sin cambio): ");
            if (!a.empty()) pt.origen = a;
            if (!b.empty()) pt.destino = b;
            if (!askScaled("Distancia (km)", 10, 1, KM_MAX, pt.km_x10, true) ||
                !askScaled("Tiempo (horas)", 100, 1, HORAS_MAX, pt.horas_x100, true) || !askPeajes(pt.peajes))
                continue;
            std::cout << (p.updateRoute(id, pt, e) ? string(GREEN) + "Ruta modificada." : string(RED) + e) << RESET << "\n";
        } else if (o == "4") {
            std::cout << (p.deleteRoute(id, e) ? string(GREEN) + "Ruta eliminada." : string(RED) + e) << RESET << "\n";
        } else if (o == "5") {
            if (!p.toggleRoute(id, e)) std::cout << RED << e << RESET << "\n";
            else std::cout << GREEN << "Ruta " << (p.st.routes.at(id).activo ? "reactivada." : "desactivada.") << RESET << "\n";
        } else {
            std::cout << "Opción no válida.\n";
        }
    }
}

static void menuParams(Pera& p) {
    const Params& m = p.st.p;
    std::cout << "\n" << BOLD << "PARÁMETROS" << RESET << "\n  Consumo: " << fixedScaled(m.consumo_x10, 1) << " km/galón\n  Precio: "
              << cop(m.precio) << " por galón\n  Velocidad (informativa): " << m.velocidad << " km/h\n";
    std::optional<ll> c, pr, v;
    if (!askScaled("Consumo km/galón", 10, 1, CONSUMO_MAX, c, true) || !askScaled("Precio del galón (COP)", 1, 0, DINERO_MAX, pr, true) ||
        !askScaled("Velocidad km/h", 1, 1, VEL_MAX, v, true))
        return;
    if (!c && !pr && !v) return;
    p.setParams(c, pr, v);
    std::cout << GREEN << "Parámetros actualizados." << RESET << "\n";
}

static void consoleQuery(Pera& p) {
    string a = ask("Ciudad origen (id): "), b = ask("Ciudad destino (id): "), e;
    QueryRes q;
    if (!p.query(a, b, q, e)) { std::cout << RED << e << RESET << "\n"; return; }
    if (a == b) { std::cout << "Origen y destino son la misma ciudad: 0 km, 0 h, $0.\n"; return; }
    if (!q.reachable) {
        std::cout << RED << "Sin ruta registrada en esta red entre " << cityLabel(p, a) << " y " << cityLabel(p, b) << "." << RESET << "\n";
        return;
    }
    std::cout << "\n" << BOLD << cityLabel(p, a) << "  →  " << cityLabel(p, b) << RESET << "\n\n";
    const char* names[5] = {"Más corta", "Más rápida", "Más económica (combustible)", "Menos peajes", "Menor costo total (comb.+peajes)"};
    std::cout << BOLD << padR("Criterio", 34) << padL("Distancia", 12) << padL("Tiempo", 14) << padL("Combustible", 14)
              << padL("Peajes", 12) << RESET << "\n";
    for (int c = 0; c < 5; ++c) {
        const PathRes& r = q.by[c];
        std::cout << padR(names[c], 34) << padL(kmTxt(r.km_x10), 12) << padL(hrTxt(r.horas_x100), 14) << padL(cop(r.combustible), 14)
                  << padL(cop(r.peajes), 12) << "\n";
    }
    for (int c = 0; c < 5; ++c) {
        std::cout << "\n" << CYAN << names[c] << RESET << ": ";
        const PathRes& r = q.by[c];
        for (size_t i = 0; i < r.cities.size(); ++i) {
            std::cout << (i ? " → " : "") << p.st.cities.at(r.cities[i]).nombre;
        }
        std::cout << "\n  rutas: " << joinBy(r.routes, ' ') << "\n";
    }
}

static void printSeries(const char* title, const Series& s, int dec, const char* unit) {
    std::cout << "\n" << BOLD << title << RESET << " (" << unit << "), n = " << s.n << "\n";
    if (s.n == 0) { std::cout << "  (sin datos)\n"; return; }
    double sc = static_cast<double>(s.scale);
    std::cout << "  mín " << num2(static_cast<double>(s.mn) / sc, dec) << "   máx " << num2(static_cast<double>(s.mx) / sc, dec)
              << "   media " << num2(s.media, dec) << "   mediana " << num2(s.mediana, dec) << "   total "
              << num2(static_cast<double>(s.total) / sc, dec) << "\n";
    ll top = *std::max_element(s.cuentas.begin(), s.cuentas.end());
    for (size_t i = 0; i < 10; ++i) {
        ll c = s.cuentas[i];
        size_t w = top ? static_cast<size_t>((c * 40 + top - 1) / top) : 0;
        std::cout << "  [" << padL(num2(s.limites[i], dec), 10) << " - " << padL(num2(s.limites[i + 1], dec), 10)
                  << (i == 9 ? "]" : ")") << " " << padR(string(w, '#'), 40) << " " << c << "\n";
    }
}

static void consoleStats(const Pera& p) {
    Stats s = p.stats();
    std::cout << "\n" << BOLD << "RESUMEN ESTADÍSTICO" << RESET << "\n";
    std::cout << "  Ciudades: " << s.ciudades << " (" << s.ciudades_activas << " activas)   Peajes: " << s.peajes << " ("
              << s.peajes_activos << " activos)\n  Rutas: " << s.rutas << " (" << s.rutas_activas << " activas, " << s.rutas_efectivas
              << " efectivas)   Componentes conexas: " << s.componentes << "\n";
    printSeries("Distancia por ruta", s.series[0], 1, "km");
    printSeries("Tiempo por ruta", s.series[1], 2, "horas");
    printSeries("Combustible por ruta", s.series[2], 0, "COP");
    printSeries("Peajes por ruta", s.series[3], 0, "COP");
    std::cout << "\n" << BOLD << "Peajes activos por departamento" << RESET << "\n";
    if (s.deptos.empty()) std::cout << "  (sin datos)\n";
    else std::cout << BOLD << "  " << padR("Departamento", 24) << padL("Peajes", 8) << padL("Tarifa total", 14) << RESET << "\n";
    for (const auto& d : s.deptos)
        std::cout << "  " << padR(cut(d.departamento, 23), 24) << padL(std::to_string(d.cantidad), 8) << padL(cop(d.tarifa_total), 14) << "\n";
    std::cout << "\n" << BOLD << "Grado de las ciudades (rutas efectivas)" << RESET << "\n";
    ll mx = s.grados.empty() ? 0 : s.grados.front().grado;
    for (const auto& g : s.grados) {
        size_t w = mx ? static_cast<size_t>(g.grado * 30 / mx) : 0;
        std::cout << "  " << padR(cut(g.nombre, 22), 23) << padL(std::to_string(g.grado), 3) << " " << string(w, '#') << "\n";
    }
    const char* tt[4] = {"distancia (km)", "tiempo (h)", "combustible (COP)", "peajes (COP)"};
    const int dd[4] = {1, 2, 0, 0};
    for (int c = 0; c < 4; ++c) {
        std::cout << "\n" << BOLD << "Rutas más altas en " << tt[c] << RESET << "\n";
        for (const auto& t : s.top[c])
            std::cout << "  " << padR(t.id, 6) << padR(cut(cityLabel(p, t.origen), 24) + " - " + cut(cityLabel(p, t.destino), 24), 52)
                      << padL(num2(t.valor, dd[c]), 12) << "\n";
        if (s.top[c].empty()) std::cout << "  (sin datos)\n";
    }
}

static int runConsole(const string& dataPath) {
    Pera p;
    string msg;
    try {
        std::cout << BOLD << "PERA - Programa Estadístico de Rutas de Automóviles" << RESET << "\n";
        if (yes(ask("¿Cargar los datos de '" + dataPath + "'? (s/n): "))) {
            string e;
            msg = p.load(dataPath, e) ? "Datos cargados: " + std::to_string(p.st.cities.size()) + " ciudades, " +
                                            std::to_string(p.st.tolls.size()) + " peajes, " + std::to_string(p.st.routes.size()) + " rutas."
                                      : "No se cargó: " + e;
        } else {
            msg = "Se empieza con datos vacíos.";
        }
        while (true) {
            std::cout << "\n" << (msg.empty() ? "" : CYAN + msg + RESET + "\n") << "\n"
                      << BOLD << "MENÚ" << RESET << (p.dirty ? string(DIM) + "  (cambios sin guardar)" + RESET : "") << "\n"
                      << " 1) Ciudades   2) Rutas   3) Peajes   4) Parámetros de combustible\n"
                         " 5) Consultar ruta A→B   6) Resumen estadístico\n"
                         " 7) Guardar   8) Cargar   9) Deshacer   10) Nuevo (vacío)   0) Salir\n";
            string o = ask("Opción: "), e;
            msg.clear();
            if (o == "0") {
                if (p.dirty && yes(ask("Hay cambios sin guardar. ¿Guardar en '" + dataPath + "'? (s/n): "))) {
                    if (!p.save(dataPath, e)) std::cout << RED << e << RESET << "\n";
                }
                break;
            } else if (o == "1") menuCities(p);
            else if (o == "2") menuRoutes(p);
            else if (o == "3") menuTolls(p);
            else if (o == "4") menuParams(p);
            else if (o == "5") consoleQuery(p);
            else if (o == "6") consoleStats(p);
            else if (o == "7" || o == "8") {
                string path = ask("Ruta del archivo [" + dataPath + "]: ");
                if (path.empty()) path = dataPath;
                if (o == "7") msg = p.save(path, e) ? "Guardado en " + path + "." : e;
                else msg = p.load(path, e) ? "Cargado desde " + path + "." : e;
            } else if (o == "9") {
                msg = p.undo(e) ? "Cambio deshecho." : e;
            } else if (o == "10") {
                if (!p.dirty || yes(ask("Hay cambios sin guardar. ¿Descartarlos? (s/n): "))) {
                    p.reset();
                    msg = "Datos vacíos.";
                }
            } else {
                msg = "Opción no válida.";
            }
        }
    } catch (const Eof&) {
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

// ================================================================ 10. main
int main(int argc, char** argv) {
    bool api = false;
    string data = "data/pera_colombia.csv";
    for (int i = 1; i < argc; ++i) {
        string a = argv[i];
        if (a == "--self-test") return selfTest();
        if (a == "--api") api = true;
        else if (a == "--data" && i + 1 < argc) data = argv[++i];
        else if (a == "--help" || a == "-h") {
            std::cout << "Uso: pera_cpp [--api] [--data ruta] [--self-test] [--help]\n"
                         "  (sin opciones)  consola interactiva\n"
                         "  --api           protocolo JSON por stdin/stdout (una línea por solicitud)\n"
                         "  --data ruta     archivo de datos por defecto (data/pera_colombia.csv)\n"
                         "  --self-test     ejecuta las pruebas internas\n";
            return 0;
        }
    }
    if (api) return runApi(data);
    initTerminal();
    return runConsole(data);
}
