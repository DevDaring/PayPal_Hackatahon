"""Integrity benchmark: labelled honest and manipulated quote sets, scored with the production analyzer.

Honest controls measure false alarms; attacks measure what is caught, blocked and recovered.
Attacks are applied to two document families: the demo templates (fixtures.py) and the 26 holdout
layouts (holdout.py), which were written independently of the forensic detectors. Hard cases that
the method is not expected to catch (a cleanly re-saved edit; an invented competitor with fresh,
unrelated metadata) are included and reported as misses rather than left out.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta
from decimal import Decimal

from . import fixtures, holdout
from .documents import ingest
from .documents.integrity import INTEGRITY_VERSION, DocInput, analyze

BENCH_VERSION = "quoteguard-integrity-v1"
_ISSUE = fixtures.EVAL_SCENARIO_DATE
MEMBERS = ["Riya Sen · Requester", "Marcus Hale · Approver"]


def _reprovenance(pdf: bytes, supplier: str) -> bytes:
    """Give a holdout layout the metadata an independent supplier would have (own person, tool and day)."""
    return fixtures.with_provenance(pdf, fixtures.provenance_for(supplier, _ISSUE))


def _edit_total(pdf: bytes, total: str, *, incremental: bool, mode: str = "edit") -> tuple[bytes, str] | None:
    """Lower the total by ~10% inside the page content. Returns None when the layout encodes the amount differently."""
    new = f"{(Decimal(total.replace(',', '')) * Decimal('0.9')).quantize(Decimal('1.00')):,.2f}"
    try:
        if mode == "patch":
            import pdfplumber

            with pdfplumber.open(io.BytesIO(pdf)) as d:
                token = next((w["text"] for w in d.pages[0].extract_words() if total in w["text"]), None)
            if token is None:
                return None
            return fixtures.tamper_pdf(pdf, [(token, token.replace(total, new))], mode="patch", incremental=incremental), new
        return fixtures.tamper_pdf(pdf, [(total, new)], mode="edit", incremental=incremental), new
    except (ValueError, KeyError, StopIteration):
        return None


def cases() -> list[dict]:
    """Each case is one purchase request: {case_id, category, kind (control|attack), expected (clear|review|block), docs, target, recover}."""
    out: list[dict] = []
    sample = fixtures.main_scenario(_ISSUE)
    sample_docs = [{"supplier": s["supplier"], "pdf": fixtures.quote_pdf(s["q"]), "total": s["q"]["total"].split("$")[1]} for s in sample]
    ho = holdout.holdout_cases()
    ho_text = [c for c in ho if c["category"] != "scanned" and c["expected"].get("total")]

    # ---- honest controls ------------------------------------------------------------------
    out.append({"case_id": "ctl-sample-set", "category": "honest competition", "kind": "control", "expected": "clear", "docs": sample_docs})
    for c in ho:
        out.append({"case_id": f"ctl-{c['case_id']}", "category": "honest single document (holdout layout)", "kind": "control", "expected": "clear",
                    "docs": [{"supplier": c["expected"].get("supplier_name") or c["case_id"], "pdf": c["pdf"](), "total": c["expected"].get("total")}]})
    for i in range(0, len(ho_text) - 2, 3):
        grp = ho_text[i:i + 3]
        names = [g["expected"]["supplier_name"] for g in grp]
        if len({n.lower() for n in names}) < 3:
            continue
        out.append({"case_id": f"ctl-ho-group-{i // 3 + 1}", "category": "honest competition (holdout layouts)", "kind": "control", "expected": "clear",
                    "docs": [{"supplier": n, "pdf": _reprovenance(g["pdf"](), n), "total": g["expected"]["total"]} for n, g in zip(names, grp)]})
    for n, (a, b) in enumerate([("Granite Supplies", "Riverbend Office"), ("Copperline Supplies", "Slowboat Office")], 1):
        docs = []
        for k, sup in enumerate((a, b)):
            q = fixtures.headset_quote(sup, "neutral", _ISSUE, unit="17.00", sub="510.00", ship="20.00", tax="0.00", total="530.00", days=5,
                                       meta={"author": ["Maya Okafor", "Owen Brennan"][k], "creator": "QuickBooks Online", "producer": "QuickBooks PDF Service",
                                             "created": datetime(2026, 10, 26 + 3 * k, 9 + 5 * k, 5)})
            docs.append({"supplier": sup, "pdf": fixtures.quote_pdf(q), "total": "530.00"})
        out.append({"case_id": f"ctl-same-software-{n}", "category": "honest: same invoicing software & template", "kind": "control", "expected": "clear", "docs": docs})
    rev = fixtures.quote_pdf(sample[1]["q"])
    from pypdf import PdfReader, PdfWriter

    w = PdfWriter(io.BytesIO(rev), incremental=True)
    w.add_metadata({"/Keywords": "approved for release"})
    buf = io.BytesIO()
    w.write(buf)
    out.append({"case_id": "ctl-metadata-only-update", "category": "honest: re-saved without content change", "kind": "control", "expected": "clear",
                "docs": [sample_docs[0], {**sample_docs[1], "pdf": buf.getvalue()}, sample_docs[2]]})

    # ---- edited bills ------------------------------------------------------------------------
    def attack(case_id, category, expected, target_idx, docs, recover=None):
        out.append({"case_id": case_id, "category": category, "kind": "attack", "expected": expected, "docs": docs, "target": docs[target_idx]["supplier"], "recover": recover})

    for i, s in enumerate(sample_docs):
        for mode, inc, cat, exp in (("edit", True, "edited bill: PDF editor, incremental save", "block"), ("patch", False, "edited bill: white-box patch, flattened", "block"),
                                    ("edit", False, "edited bill: clean full re-save (hard)", "block")):
            r = _edit_total(s["pdf"], s["total"], incremental=inc, mode=mode)
            if r:
                docs = [dict(d) for d in sample_docs]
                docs[i] = {**s, "pdf": r[0], "total": r[1]}
                attack(f"atk-{mode}{'-inc' if inc else '-flat'}-{sample[i]['key']}", cat, exp, i, docs, recover=s["total"] if inc else None)
        q = {**sample[i]["q"], "retype": {"total": "Times-Roman"}}
        docs = [dict(d) for d in sample_docs]
        docs[i] = {**s, "pdf": fixtures.quote_pdf(q)}
        attack(f"atk-retype-{sample[i]['key']}", "edited bill: amount retyped in another font", "review", i, docs)
    for c in ho_text[:12]:
        sup, total = c["expected"]["supplier_name"], c["expected"]["total"]
        base = _reprovenance(c["pdf"](), sup)
        for mode, inc, cat in (("edit", True, "edited bill on holdout layout: incremental"), ("patch", False, "edited bill on holdout layout: white-box patch")):
            r = _edit_total(base, total, incremental=inc, mode=mode)
            if r:
                attack(f"atk-ho-{mode}-{c['case_id']}", cat, "block", 0, [{"supplier": sup, "pdf": r[0], "total": r[1]}], recover=total if inc else None)

    # ---- fabricated competition ----------------------------------------------------------------
    day = datetime.combine(_ISSUE - timedelta(days=2), datetime.min.time())
    word = ("Microsoft Word for Microsoft 365", "Microsoft® Word for Microsoft 365")

    def q(sup, theme, total, author, minute, contact="", doc_id=None, creator=word, day_offset=0):
        sub = f"{Decimal(total) - Decimal('40.00'):.2f}"
        return fixtures.quote_pdf(fixtures.headset_quote(sup, theme, _ISSUE, unit=f"{Decimal(sub) / 30:.2f}", sub=sub, ship="40.00", tax="0.00", total=total, days=5,
                                                         contact=contact, doc_id=doc_id, quote_no=f"Q-{abs(hash(sup)) % 9000 + 1000}",
                                                         meta={"author": author, "creator": creator[0], "producer": creator[1], "created": day + timedelta(days=day_offset, hours=10, minutes=minute)}))

    def doc_id_of(pdf):
        import re

        return bytes.fromhex(re.search(rb"/ID\s*\[\s*<([0-9a-fA-F]+)>", pdf).group(1).decode())

    favoured = ("Pinecrest Audio", "neutral", "585.00")
    attack("atk-cover-quotes-demo", "fabricated competition: author + file + phone", "block", 0,
           [{"supplier": d["supplier"], "pdf": d["pdf"], "total": t} for d, t in zip(fixtures.cover_quote_set(_ISSUE), ("585.00", "612.00", "629.00"))])
    a = q(*favoured, "Jordan Vale", 0)
    attack("atk-cover-shared-author", "fabricated competition: shared author", "block", 0,
           [{"supplier": favoured[0], "pdf": a, "total": "585.00"}, {"supplier": "Maple Ridge Tech", "pdf": q("Maple Ridge Tech", "violet", "611.00", "Jordan Vale", 40, day_offset=1), "total": "611.00"},
            {"supplier": "Quarry Lane Supply", "pdf": q("Quarry Lane Supply", "harbor", "626.00", "S. Brandt", 300, creator=_tool(2), day_offset=-1), "total": "626.00"}])
    b = q(*favoured, "Jordan Vale", 0)
    attack("atk-cover-shared-file", "fabricated competition: copied from the same file", "block", 0,
           [{"supplier": favoured[0], "pdf": b, "total": "585.00"}, {"supplier": "Maple Ridge Tech", "pdf": q("Maple Ridge Tech", "violet", "611.00", "Office", 900, doc_id=doc_id_of(b), creator=_tool(3)), "total": "611.00"},
            {"supplier": "Quarry Lane Supply", "pdf": q("Quarry Lane Supply", "harbor", "626.00", "S. Brandt", 300, creator=_tool(2), day_offset=-1), "total": "626.00"}])
    attack("atk-cover-shared-phone", "fabricated competition: shared phone number", "block", 0,
           [{"supplier": favoured[0], "pdf": q(*favoured, "Jordan Vale", 0, contact="Tel +1 (503) 555-0187"), "total": "585.00"},
            {"supplier": "Maple Ridge Tech", "pdf": q("Maple Ridge Tech", "violet", "611.00", "Lena Ruiz", 700, contact="Phone: 503-555-0187", creator=_tool(4), day_offset=-2), "total": "611.00"},
            {"supplier": "Quarry Lane Supply", "pdf": q("Quarry Lane Supply", "harbor", "626.00", "S. Brandt", 300, creator=_tool(2), day_offset=-1), "total": "626.00"}])
    attack("atk-cover-shared-email", "fabricated competition: shared email address", "block", 0,
           [{"supplier": favoured[0], "pdf": q(*favoured, "Jordan Vale", 0, contact="quotes@pinecrest-audio.example"), "total": "585.00"},
            {"supplier": "Maple Ridge Tech", "pdf": q("Maple Ridge Tech", "violet", "611.00", "Lena Ruiz", 700, contact="Replies: quotes@pinecrest-audio.example", creator=_tool(4), day_offset=-2), "total": "611.00"},
            {"supplier": "Quarry Lane Supply", "pdf": q("Quarry Lane Supply", "harbor", "626.00", "S. Brandt", 300, creator=_tool(2), day_offset=-1), "total": "626.00"}])
    attack("atk-insider-authored", "fabricated competitor written by the requester", "block", 1,
           [sample_docs[1], {"supplier": "Fernhill Electronics", "pdf": q("Fernhill Electronics", "violet", "598.00", "Riya Sen", 200, creator=_tool(1)), "total": "598.00"}, sample_docs[2]])
    attack("atk-cover-created-together", "fabricated competition: same tool, minutes apart only", "review", 0,
           [{"supplier": favoured[0], "pdf": q(*favoured, "Jordan Vale", 0), "total": "585.00"},
            {"supplier": "Maple Ridge Tech", "pdf": q("Maple Ridge Tech", "violet", "611.00", "Lena Ruiz", 6), "total": "611.00"},
            {"supplier": "Quarry Lane Supply", "pdf": q("Quarry Lane Supply", "harbor", "626.00", "S. Brandt", 300, creator=_tool(2), day_offset=-1), "total": "626.00"}])
    attack("atk-cover-clean-metadata", "fabricated competition: fresh, unrelated metadata (hard)", "block", 0,
           [{"supplier": favoured[0], "pdf": q(*favoured, "Jordan Vale", 0), "total": "585.00"},
            {"supplier": "Maple Ridge Tech", "pdf": q("Maple Ridge Tech", "violet", "611.00", "Lena Ruiz", 700, creator=_tool(4), day_offset=-2), "total": "611.00"},
            {"supplier": "Quarry Lane Supply", "pdf": q("Quarry Lane Supply", "harbor", "626.00", "S. Brandt", 300, creator=_tool(2), day_offset=-1), "total": "626.00"}])
    return out


def _tool(i: int) -> tuple[str, str]:
    return fixtures._TOOLS[i % len(fixtures._TOOLS)]


def run() -> dict:
    results = []
    for c in cases():
        docs = []
        for n, d in enumerate(c["docs"]):
            parsed = ingest.parse_isolated(d["pdf"])
            text = "\n".join(p["text"] for p in parsed.get("pages", []))
            docs.append(DocInput(key=f"d{n}", supplier=d["supplier"], text=text, forensics=parsed.get("forensics"), total=Decimal(d["total"].replace(",", "")) if d.get("total") else None))
        r = analyze(docs, MEMBERS)
        target_key = next((x.key for x in docs if x.supplier == c.get("target")), None)
        recovered = None
        if c.get("recover"):
            detail = " ".join(f["detail"] for f in r["findings"] if f["kind"] == "revision_edit")
            recovered = c["recover"] in detail
        results.append({"case_id": c["case_id"], "category": c["category"], "kind": c["kind"], "expected": c["expected"], "decision": r["overall"],
                        "target_status": r["per_quote"].get(target_key, {}).get("status") if target_key else None, "recovered_original": recovered,
                        "findings": [{"kind": f["kind"], "severity": f["severity"], "title": f["title"]} for f in r["findings"] if f["severity"] != "low"],
                        "screens": r.get("screens"), "documents": len(docs)})
    return {"version": BENCH_VERSION, "analyzer": INTEGRITY_VERSION, "summary": summarize(results), "cases": results}


def summarize(results: list[dict]) -> dict:
    ctl = [r for r in results if r["kind"] == "control"]
    atk = [r for r in results if r["kind"] == "attack"]
    rec = [r for r in atk if r["recovered_original"] is not None]
    by_cat: dict[str, dict] = {}
    for r in atk:
        b = by_cat.setdefault(r["category"], {"cases": 0, "caught": 0, "blocked": 0, "expected": r["expected"]})
        b["cases"] += 1
        b["caught"] += r["decision"] != "clear"
        b["blocked"] += r["decision"] == "block"
    return {
        "controls": len(ctl), "control_documents": sum(r["documents"] for r in ctl), "false_alarms": sum(r["decision"] != "clear" for r in ctl),
        "attacks": len(atk), "caught": sum(r["decision"] != "clear" for r in atk), "blocked": sum(r["decision"] == "block" for r in atk),
        "decision_matches_label": sum(r["decision"] == r["expected"] for r in results), "cases": len(results),
        "originals_recovered": sum(bool(r["recovered_original"]) for r in rec), "recoverable": len(rec),
        "by_category": by_cat,
        "missed": [r["case_id"] for r in atk if r["decision"] == "clear"],
        "false_alarm_cases": [r["case_id"] for r in ctl if r["decision"] != "clear"],
        "digest": hashlib.sha256(repr([(r["case_id"], r["decision"]) for r in results]).encode()).hexdigest()[:16],
    }
