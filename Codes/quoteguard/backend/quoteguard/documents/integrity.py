"""Document integrity: deterministic forensics for edited bills and fabricated competition.

Two questions, answered from the PDF files themselves (never from the model):

1. Was this document altered after it was created?  (per document)
   - Incremental-update recovery: every earlier revision of an incrementally saved PDF is still in the file.
     We re-read it and diff it against what is shown now ("Total $640.00 → $540.00").
   - Opaque patches: a filled shape drawn *after* the text it covers (content-stream order), with new text on top.
   - Retyped amounts: an amount set in a different font family from its own label and from the other amounts.
2. Are the "competing" quotes really independent?  (across documents from different suppliers)
   - Provenance links: shared original document ID, shared author, shared phone/email/bank details,
     authored by a member of the buying workspace, created minutes apart with the same tool.
   - Template resemblance: Broder's w-shingling resemblance on masked text (supporting only — many
     suppliers legitimately use the same invoicing software).
   - Bid screens from the bid-rigging literature (Huber & Imhof, 2019): coefficient of variation and
     relative distance. With a handful of quotes these are context, never a verdict on their own.

Severity → policy: high → fail, medium → unknown (needs review), low → listed as context only.
"""

from __future__ import annotations

import difflib
import re
import statistics
from dataclasses import dataclass, field
from decimal import Decimal

INTEGRITY_VERSION = "integrity-v2"
_MONEY = re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d{2})?|\b\d[\d,]*\.\d{2}\b")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?:\b(?:tel|telephone|phone|ph|mobile|cell|call|fax|whatsapp)\b[.:#\s]*|(?=\+))(\+?[\d(][\d\s().-]{8,22}\d)", re.I)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b")
_ACCOUNT = re.compile(r"(?:account|acct|a/c|routing|sort code)[^\d\n]{0,20}([\d -]{6,20}\d)", re.I)
_EDITORS = ("pdf-xchange", "ilovepdf", "smallpdf", "sejda", "pdfescape", "pdf editor", "pdfelement", "foxit phantom", "nitro", "pdffiller", "docfly", "sodapdf")
_GENERIC_AUTHORS = {"", "anonymous", "user", "admin", "administrator", "owner", "author", "unknown", "microsoft office user", "windows user", "sales", "accounts", "office"}
_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class DocInput:
    key: str  # quote id
    supplier: str
    text: str
    forensics: dict | None
    total: Decimal | None = None
    filename: str = ""


@dataclass
class Finding:
    id: str
    kind: str
    severity: str  # high | medium | low
    title: str
    detail: str
    quotes: list[str]
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "severity": self.severity, "title": self.title, "detail": self.detail, "quotes": self.quotes, "evidence": self.evidence}


def _norm_name(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split())


def _family(font: str | None) -> str:
    f = (font or "").lower()
    f = re.sub(r"(ps)?mt$", "", f.split(",")[0])
    return re.split(r"[-_ ]", f)[0]


def _pdf_time(s: str | None):
    from datetime import datetime, timezone

    m = re.match(r"D?:?(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", s or "")
    if not m:
        return None
    y, mo, d, h, mi, se = (int(x) if x else 0 for x in m.groups())
    try:
        return datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc)
    except ValueError:
        return None


def _contacts(text: str) -> dict[str, set[str]]:
    phones = {re.sub(r"\D", "", p) for p in _PHONE.findall(text)}
    return {
        "email": {e.lower() for e in _EMAIL.findall(text)},
        "phone": {p[-10:] for p in phones if 10 <= len(p) <= 15},
        "bank": {re.sub(r"\s", "", x) for x in _IBAN.findall(text)} | {re.sub(r"\D", "", x) for x in _ACCOUNT.findall(text)},
    }


def _shingles(text: str, supplier: str, w: int = 4) -> set[tuple[str, ...]]:
    t = text.lower()
    for tok in _norm_name(supplier).split():
        if len(tok) > 2:
            t = re.sub(rf"\b{re.escape(tok)}\b", " ", t)
    t = _EMAIL.sub(" ", t)
    t = re.sub(r"\d", "#", t)
    words = re.findall(r"[a-z#]+", t)
    return {tuple(words[i:i + w]) for i in range(max(0, len(words) - w + 1))}


def resemblance(a: set, b: set) -> float:
    """Broder (1997) resemblance |A∩B| / |A∪B| of w-shingle sets."""
    return len(a & b) / len(a | b) if a and b else 0.0


def bid_screens(totals: list[Decimal]) -> dict | None:
    """Coefficient of variation and relative distance (Huber & Imhof, 2019) over the quoted totals."""
    bids = sorted(float(t) for t in totals if t is not None and t > 0)
    if len(bids) < 3:
        return None
    mean, sd = statistics.mean(bids), statistics.stdev(bids)
    losing_sd = statistics.stdev(bids[1:])
    cv = sd / mean if mean else None
    rd = (bids[1] - bids[0]) / losing_sd if losing_sd else None
    pattern = bool(rd is not None and cv is not None and rd > 1 and cv < 0.05)
    return {"n": len(bids), "cv": round(cv, 4) if cv is not None else None, "rd": round(rd, 3) if rd is not None else None, "cover_bid_pattern": pattern,
            "note": "Context only: with few quotes these screens are weak signals. A low CV with RD > 1 means the losing quotes sit tightly together above an isolated winner — the cover-bidding shape."}


# ----------------------------------------------------------------------------- per document --

def _line_diff(before: str, after: str) -> list[tuple[str, str]]:
    a = [ln.strip() for ln in before.splitlines() if ln.strip()]
    b = [ln.strip() for ln in after.splitlines() if ln.strip()]
    pairs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        old, new = a[i1:i2], b[j1:j2]
        for k in range(max(len(old), len(new))):
            pairs.append((old[k] if k < len(old) else "", new[k] if k < len(new) else ""))
    return pairs


def document_findings(d: DocInput, member_names: list[str], next_id) -> list[Finding]:
    fo = d.forensics or {}
    out: list[Finding] = []
    if not fo or "error" in fo:
        return out
    # 1. Earlier revisions preserved by incremental saves.
    for rev in fo.get("previous_revisions") or []:
        if rev.get("text") is None:
            out.append(Finding(next_id(), "revision_unreadable", "low", "Earlier revision present", f"The file was saved again after creation (revision {rev['index']} of {fo.get('revision_count')}); the earlier revision could not be read.", [d.key]))
            continue
        pairs = _line_diff(rev["text"], d.text)
        money = [(o, n) for o, n in pairs if _MONEY.search(o) or _MONEY.search(n)]
        payee = [(o, n) for o, n in pairs if any(_contacts(x)[k] for x in (o, n) for k in ("email", "bank"))]
        changes = [{"before": o, "after": n} for o, n in (money + [p for p in payee if p not in money] or pairs)[:8]]
        if money or payee:
            tokens = []
            for o, n in money[:4]:
                mo, mn = _MONEY.findall(o), _MONEY.findall(n)
                label = re.split(r"[:(]", n or o)[0].strip()[:40]
                tokens.append(f"{label}: {mo[-1] if mo else '—'} → {mn[-1] if mn else '—'}")
            out.append(Finding(next_id(), "revision_edit", "high", "Amounts changed after the document was created",
                               "The PDF still contains its earlier revision. Recovered original vs. shown now: " + "; ".join(tokens or [f"{len(payee)} payment-detail line(s) changed"]) + ".",
                               [d.key], {"changes": changes, "revision": rev["index"], "revisions": fo.get("revision_count")}))
        elif pairs:
            out.append(Finding(next_id(), "revision_text", "medium", "Text changed after the document was created",
                               f"{len(pairs)} line(s) differ from the earlier revision kept in the file.", [d.key], {"changes": changes, "revision": rev["index"]}))
        else:
            out.append(Finding(next_id(), "revision_meta", "low", "Saved again without visible changes", "An incremental update changed only metadata or structure, not the text.", [d.key]))
    # 2. Opaque patches drawn over text.
    for p in fo.get("patches") or []:
        numeric = bool(re.search(r"\d", p.get("hidden", "")))
        out.append(Finding(next_id(), "overlay_patch", "high" if numeric else "medium", "Text hidden under an opaque box",
                           f"Page {p['page']}: “{p['hidden']}” is covered by a filled box drawn after it" + (f", with “{p['replacement']}” typed on top." if p.get("replacement") else "."),
                           [d.key], {"page": p["page"], "bbox": p["bbox"], "hidden": p["hidden"], "replacement": p.get("replacement")}))
    # 3. Amounts set in a font that matches neither their own label nor the other amounts.
    mf = fo.get("money_fonts") or []
    fams = [_family(m["font"]) for m in mf]
    for i, m in enumerate(mf):
        others = fams[:i] + fams[i + 1:]
        if len(others) < 2 or not m.get("label_font"):
            continue
        fam = fams[i]
        if fam != _family(m["label_font"]) and others.count(fam) == 0:
            out.append(Finding(next_id(), "font_outlier", "medium", "Amount typed in a different font",
                               f"“{m['text']}” after “{m.get('label') or 'its label'}” is set in {m['font']}, while its label uses {m['label_font']} and every other amount uses {max(set(others), key=others.count)}.",
                               [d.key], {"page": m["page"], "bbox": m["bbox"], "text": m["text"], "font": m["font"], "label_font": m["label_font"]}))
    # 4. Authored by someone inside the buying organisation.
    meta = fo.get("meta") or {}
    author = _norm_name(meta.get("author", ""))
    if author and author not in _GENERIC_AUTHORS:
        at = set(author.split())
        for name in member_names:
            nt = set(_norm_name(name).split())
            if len(at & nt) >= 2:
                out.append(Finding(next_id(), "author_is_member", "high", "Written by someone in your workspace",
                                   f"The quote says it is from {d.supplier}, but its document author is “{meta.get('author')}”, matching workspace member “{name}”.",
                                   [d.key], {"author": meta.get("author"), "member": name}))
                break
    # 5. Context: edited with a PDF editor / modified long after creation.
    prod = (meta.get("producer") or "").lower()
    if any(e in prod for e in _EDITORS) and _family(prod) != _family((meta.get("creator") or "").lower()):
        out.append(Finding(next_id(), "editor_tool", "low", "Last saved by a PDF editing tool", f"Created with “{meta.get('creator') or 'unknown'}”, last saved by “{meta.get('producer')}”.", [d.key]))
    c0, c1 = _pdf_time(meta.get("creationdate")), _pdf_time(meta.get("moddate"))
    if c0 and c1 and (c1 - c0).total_seconds() > 86400:
        out.append(Finding(next_id(), "late_modification", "low", "Modified after creation", f"Created {c0:%Y-%m-%d %H:%M}, modified {c1:%Y-%m-%d %H:%M} UTC.", [d.key]))
    return out


# ------------------------------------------------------------------------------ cross document --

def pair_signals(a: DocInput, b: DocInput) -> list[dict]:
    fa, fb = a.forensics or {}, b.forensics or {}
    ma, mb = fa.get("meta") or {}, fb.get("meta") or {}
    sig = []
    if fa.get("doc_id") and fa.get("doc_id") == fb.get("doc_id"):
        sig.append({"kind": "shared_document_id", "strength": "high", "detail": "Both files descend from the same original PDF (identical permanent document ID)."})
    au, bu = _norm_name(ma.get("author", "")), _norm_name(mb.get("author", ""))
    if au and au == bu and au not in _GENERIC_AUTHORS:
        sig.append({"kind": "shared_author", "strength": "high", "detail": f"Both were written by “{ma.get('author')}”."})
    ca, cb = _contacts(a.text), _contacts(b.text)
    for k, label in (("phone", "phone number"), ("email", "email address"), ("bank", "bank account")):
        shared = ca[k] & cb[k]
        if shared:
            sig.append({"kind": f"shared_{k}", "strength": "high", "detail": f"Both list the same {label}: {sorted(shared)[0]}."})
    ta, tb = _pdf_time(ma.get("creationdate")), _pdf_time(mb.get("creationdate"))
    same_tool = ma.get("creator") and ma.get("creator") == mb.get("creator")
    if ta and tb and same_tool and abs((ta - tb).total_seconds()) <= 15 * 60:
        mins = abs((ta - tb).total_seconds()) / 60
        sig.append({"kind": "created_together", "strength": "medium", "detail": f"Created {mins:.0f} min apart with the same tool ({ma.get('creator')})."})
    r = resemblance(_shingles(a.text, a.supplier), _shingles(b.text, b.supplier))
    if r >= 0.8:
        sig.append({"kind": "same_template", "strength": "low", "detail": f"Near-identical wording and layout (resemblance {r:.2f}); common when suppliers use the same invoicing software.", "value": round(r, 3)})
    return sig


def supplier_key(name: str) -> str:
    return _norm_name(re.sub(r"\s*\(lab copy \d+\)", "", name or ""))


def analyze(docs: list[DocInput], member_names: list[str], history: list[dict[str, float]] | None = None) -> dict:
    """history: past tenders in this workspace as {supplier_key: total}; enables the recurring-group cartel model."""
    n = [0]

    def next_id():
        n[0] += 1
        return f"F{n[0]}"

    findings: list[Finding] = []
    for d in docs:
        findings += document_findings(d, member_names, next_id)
    links = []
    for i, a in enumerate(docs):
        for b in docs[i + 1:]:
            if _norm_name(a.supplier) == _norm_name(b.supplier):
                continue  # revisions from one supplier are not a competition question
            sig = pair_signals(a, b)
            if not sig:
                continue
            ranks = sorted((_RANK[s["strength"]] for s in sig), reverse=True)
            level = "high" if ranks[0] == 3 else ("medium" if ranks[0] == 2 and len(ranks) >= 2 else None)
            links.append({"a": a.key, "b": b.key, "signals": sig, "level": level})
    # Connected components over decisive links.
    parent = {d.key: d.key for d in docs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for ln in links:
        if ln["level"]:
            parent[find(ln["a"])] = find(ln["b"])
    groups: dict[str, list[str]] = {}
    for d in docs:
        groups.setdefault(find(d.key), []).append(d.key)
    clusters = []
    by_key = {d.key: d for d in docs}
    for members in groups.values():
        if len(members) < 2:
            continue
        inner = [ln for ln in links if ln["a"] in members and ln["b"] in members and ln["level"]]
        level = "high" if any(ln["level"] == "high" for ln in inner) else "medium"
        kinds = sorted({s["kind"] for ln in inner for s in ln["signals"] if s["strength"] != "low"})
        names = [by_key[k].supplier for k in members]
        f = Finding(next_id(), "not_independent", level, "Competing quotes are not independent",
                    f"{', '.join(names[:-1])} and {names[-1]} are presented as competitors but share an origin. "
                    + " ".join(f"{by_key[ln['a']].supplier} ↔ {by_key[ln['b']].supplier}: " + "; ".join(s["detail"].rstrip(".") for s in ln["signals"] if s["strength"] != "low") + "." for ln in inner)[:900],
                    members, {"signals": kinds})
        findings.append(f)
        clusters.append({"quotes": members, "level": level, "finding": f.id})
    screens = bid_screens([d.total for d in docs if d.total is not None])
    # Recurring supplier groups: the cartel-pattern model trained on proven cartel cases (research/cartel.py).
    from ..research import cartel

    current = {supplier_key(d.supplier): float(d.total) for d in docs if d.total}
    keys = {supplier_key(d.supplier): d.key for d in docs}
    names = {supplier_key(d.supplier): re.sub(r"\s*\(lab copy \d+\)", "", d.supplier) for d in docs}
    groups = cartel.recurring_groups(current, history or []) if len(current) >= 3 else []
    for g in groups[:3]:
        g["names"] = [names[k] for k in g["suppliers"]]
        g["winner_names"] = [names.get(w, w) for w in g["winners"]]
        if g["probability"] >= 0.5:
            f = Finding(next_id(), "cartel_pattern", "medium", "Recurring group bids like proven cartels",
                        f"{', '.join(g['names'])} have quoted together in {g['joint_tenders']} purchases with {g['rotation']} different winners. Their bid pattern scores "
                        f"{g['probability']:.2f} on a model trained on proven cartel cases (threshold 0.50); strongest signals: " + ", ".join(d["screen"] for d in g["drivers"][:2]) + ".",
                        [keys[k] for k in g["suppliers"]], {"probability": g["probability"], "joint_tenders": g["joint_tenders"], "winners": [names.get(w, w) for w in g["winners"]]})
            findings.append(f)
            g["finding"] = f.id
    # Per-quote verdict for the policy engine.
    per_quote = {}
    compromised = [c for c in clusters if c["level"] == "high"]
    for d in docs:
        mine = [f for f in findings if d.key in f.quotes and f.severity in ("high", "medium")]
        status = "fail" if any(f.severity == "high" for f in mine) else ("unknown" if mine else "pass")
        detail = " ".join(f"{f.title}: {f.detail}" for f in sorted(mine, key=lambda f: -_RANK[f.severity])[:2])
        if status == "pass" and (not d.forensics or "error" in d.forensics):
            status, detail = "unknown", "The file's structure could not be assessed for editing, so integrity cannot be confirmed."
        elif status == "pass" and compromised:
            others = [by_key[k].supplier for c in compromised for k in c["quotes"]]
            status, detail = "unknown", f"The competing quotes from {', '.join(others)} are not independent, so this comparison is not a genuine competition. Obtain an independently sourced quote before approval."
            mine = [f for f in findings if f.kind == "not_independent"]
        if status == "pass":
            ctx = [f for f in findings if d.key in f.quotes]
            detail = "No signs of editing or shared origin with competing quotes." + (f" Context: {ctx[0].title.lower()}." if ctx else "")
        per_quote[d.key] = {"status": status, "detail": detail, "findings": [f.id for f in mine]}
    worst = max((_RANK[f.severity] for f in findings if f.severity != "low"), default=0)
    return {"version": INTEGRITY_VERSION, "overall": {3: "block", 2: "review"}.get(worst, "clear"), "findings": [f.as_dict() for f in findings],
            "links": links, "clusters": clusters, "screens": screens, "per_quote": per_quote, "cartel_model": {"groups": groups[:3], "model": cartel.model()["name"], "history_tenders": len(history or [])},
            "documents": {d.key: {"supplier": d.supplier, "filename": d.filename, "meta": (d.forensics or {}).get("meta"), "revisions": (d.forensics or {}).get("revision_count"),
                                  "doc_id": (d.forensics or {}).get("doc_id"), "assessed": bool(d.forensics and "error" not in d.forensics)} for d in docs}}
