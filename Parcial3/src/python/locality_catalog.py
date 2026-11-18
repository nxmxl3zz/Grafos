"""Search the bundled DANE populated-place snapshot without network requests."""
import json
import unicodedata
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / 'data/localities_colombia.json'


def normalize(value):
    text = unicodedata.normalize('NFKD', value.casefold())
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


class LocalityCatalog(list):
    def __init__(self, records):
        super().__init__(records)
        self.index = [(normalize(p['nombre']), normalize(p['municipio']), normalize(p['departamento'])) for p in self]


def load_catalog(path=DEFAULT_PATH):
    with Path(path).open(encoding='utf-8') as f:
        return LocalityCatalog(json.load(f)['localidades'])


def search_localities(records, query, limit=20):
    """Return at most limit named settlements; every input word must match a field."""
    terms = normalize(query).split()
    if not terms or limit <= 0:
        return []
    index = records.index if isinstance(records, LocalityCatalog) else [
        (normalize(p['nombre']), normalize(p['municipio']), normalize(p['departamento'])) for p in records]
    matches = []
    for record, fields in zip(records, index):
        if all(any(term in field for field in fields) for term in terms):
            rank = (not fields[0].startswith(terms[0]), fields[0], fields[2], fields[1], record['id'])
            matches.append((rank, record))
    matches.sort(key=lambda item: item[0])
    return [record for _, record in matches[:limit]]
