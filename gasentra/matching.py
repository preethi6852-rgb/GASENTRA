"""Content matching: compares outgoing text with what the agent read (exact, normalised, entity)."""
import json
import re
import unicodedata

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")


def normalize(text):
    t = unicodedata.normalize("NFKC", str(text)).lower()
    t = re.sub(r"[^a-z0-9@.\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def numbers_in(text):
    """Digit strings of length >= 4 with thousands separators removed ('90,000' -> '90000')."""
    out = set()
    for m in re.findall(r"\d[\d,]*\d|\d", str(text)):
        d = m.replace(",", "")
        if len(d) >= 4:
            out.add(d)
    return out


def _add(ents, field, value):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        d = str(int(value))
        if len(d) >= 4:
            ents.append({"field": field, "kind": "number", "value": d})
    elif isinstance(value, str):
        v = value.strip()
        if EMAIL_RE.fullmatch(v):
            ents.append({"field": field, "kind": "email", "value": v.lower()})
        elif v.isdigit():
            if len(v) >= 4:
                ents.append({"field": field, "kind": "number", "value": v})
        else:
            n = normalize(v)
            if len(n) >= 4:
                ents.append({"field": field, "kind": "text", "value": n})


def fingerprint(text):
    """Stores what we need to recognise this content later, without keeping raw structure."""
    ents = []
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        for k, v in parsed.items():
            _add(ents, k, v)
    else:
        for e in EMAIL_RE.findall(text):
            ents.append({"field": "text", "kind": "email", "value": e.lower()})
        for d in numbers_in(text):
            ents.append({"field": "text", "kind": "number", "value": d})
        for m in NAME_RE.findall(text):
            ents.append({"field": "text", "kind": "text", "value": normalize(m)})
    seen, uniq = set(), []
    for e in ents:
        key = (e["field"], e["kind"], e["value"])
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return {"norm": normalize(text), "entities": uniq}


def _mask(value):
    return value[:2] + "***" if len(value) > 2 else "***"


def match(outgoing, fingerprints, min_chars=30, strong_fields=2):
    """Returns {'strength': strong|weak|none, 'matched_fields': [...], 'exact': bool}."""
    out_norm = normalize(outgoing)
    out_nums = numbers_in(outgoing)
    matched, exact = {}, False
    for fp in fingerprints:
        n = fp["norm"]
        if len(n) >= min_chars and n in out_norm:
            exact = True
        for e in fp["entities"]:
            hit = e["value"] in out_nums if e["kind"] == "number" else e["value"] in out_norm
            if hit:
                matched[e["field"]] = {"field": e["field"], "kind": e["kind"], "preview": _mask(e["value"])}
    if exact or len(matched) >= strong_fields:
        strength = "strong"
    elif matched:
        strength = "weak"
    else:
        strength = "none"
    return {"strength": strength, "exact": exact, "matched_fields": list(matched.values())}
