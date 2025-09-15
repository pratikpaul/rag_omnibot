import glob
import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from omnibot.config.constants import RAW_FHIR_GLOB, FLAT_DIR, WRITE_JSONL
# from collections import OrderedDict

# ------------ camelCase → spaced ------------
camel_pattern1 = re.compile(r'(.)([A-Z][a-z]+)')
camel_pattern2 = re.compile(r'([a-z0-9])([A-Z])')
def split_camel(text: str) -> str:
    new_text = camel_pattern1.sub(r'\1 \2', text)
    new_text = camel_pattern2.sub(r'\1 \2', new_text)
    return new_text

# ------------ FHIR canonicalizers ------------
def canon_money(m: Dict[str, Any]) -> str:
    v = m.get("value"); c = m.get("currency")
    return f"{v} {c}" if v is not None and c else (str(v) if v is not None else "")

def canon_period(p: Dict[str, Any]) -> str:
    s = p.get("start"); e = p.get("end")
    if s and e: return f"{s}..{e}"
    return s or e or ""

def canon_quantity(q: Dict[str, Any]) -> str:
    v = q.get("value"); u = q.get("unit") or q.get("code") or q.get("system")
    return f"{v} {u}".strip() if v is not None else ""

def canon_codeable_concept(cc: Dict[str, Any]) -> str:
    txt = cc.get("text")
    if txt: return txt
    coding = cc.get("coding") or []
    if coding:
        c = coding[0]
        sys = c.get("system"); code = c.get("code"); disp = c.get("display")
        parts = [p for p in [sys, code, disp] if p]
        return " | ".join(parts)
    return ""

def canon_reference(r: Dict[str, Any]) -> str:
    # prefer "display" but keep the reference
    disp = r.get("display"); ref = r.get("reference")
    return disp or ref or ""

def canon_value(v: Any, key_path: str) -> Any:
    # Special tweak from your original: resourceType → "resource Type"
    if key_path.endswith("resource Type") and isinstance(v, str):
        return split_camel(v)

    if isinstance(v, dict):
        # detect FHIR mini types
        if set(v.keys()) >= {"value","currency"}:       return canon_money(v)
        if "start" in v or "end" in v:                  return canon_period(v)
        if "unit" in v or "value" in v:                 return canon_quantity(v)
        if "coding" in v or "text" in v:                return canon_codeable_concept(v)
        if "reference" in v or "display" in v:          return canon_reference(v)
    if isinstance(v, bool):  return "True" if v else "False"
    return v

# ------------ Flatten (stable, sorted) ------------
def flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        # sort keys for stable output
        for k in sorted(obj.keys(), key=str):
            kp = f"{prefix}{split_camel(k)} "
            out.update(flatten(obj[k], kp))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}{i} "))
    else:
        key = prefix.rstrip()
        out[key] = canon_value(obj, key)
    return out

# ------------ Derived EOB fields ------------
def derive_eob_summary(eob: Dict[str, Any]) -> Dict[str, Any]:
    # claim_id
    claim_ref = (((eob.get("claim") or {}).get("reference")) or "")
    m = re.search(r"(?:Claim/)?([A-Za-z0-9\-]+)", claim_ref)
    claim_id = m.group(1) if m else ""

    # eob_id
    eob_id = eob.get("id") or ""

    # dates
    created = eob.get("created") or ""
    bill_start = (((eob.get("billablePeriod") or {}).get("start")) or "")
    bill_end   = (((eob.get("billablePeriod") or {}).get("end")) or "")

    # status / insurer / provider (display|reference)
    status  = eob.get("status") or ""
    insurer = canon_reference(eob.get("insurer") or {})
    prov    = canon_reference(eob.get("provider") or {})

    # totals at claim-level (submitted/allowed/benefit/payment/deductible/copay/coinsurance)
    totals = {}
    for t in eob.get("total", []) or []:
        cat = (((t.get("category") or {}).get("coding") or [{}])[0].get("code")) or t.get("category",{}).get("text")
        amt = t.get("amount")
        if cat and amt:
            totals[cat] = canon_money(amt)

    # fallback: sum line-level adjudications if claim-level not present
    def sum_adj(code_set: set[str]) -> float:
        s = 0.0
        for item in eob.get("item", []) or []:
            for adj in item.get("adjudication", []) or []:
                code = (((adj.get("category") or {}).get("coding") or [{}])[0].get("code")) or ""
                if code in code_set:
                    a = adj.get("amount", {})
                    try: s += float(a.get("value", 0.0))
                    except: pass
        return s

    def get_total_val(key: str) -> Optional[str]:
        v = totals.get(key)
        if v: return v
        # if not present at claim level, compute for selected categories
        if key == "deductible":  val = sum_adj({"deductible"})
        elif key == "copay":     val = sum_adj({"copay"})
        elif key == "coinsurance": val = sum_adj({"coinsurance"})
        else: return None
        return str(round(val, 2))

    deductible  = get_total_val("deductible")
    copay       = get_total_val("copay")
    coinsurance = get_total_val("coinsurance")

    # member paid = deductible + copay + coinsurance (string sums → float best-effort)
    def f2(x):
        if not x: return 0.0
        try:
            return float(str(x).split()[0])  # handle "12.34 USD"
        except:
            return 0.0
    member_paid = round(f2(deductible) + f2(copay) + f2(coinsurance), 2)

    return {
        "Claim Reference": f"Claim/{claim_id}" if claim_id else "",
        "EOB ID": eob_id,
        "Created": created,
        "Billable Period Start": bill_start,
        "Billable Period End": bill_end,
        "Status": status,
        "Insurer": insurer,
        "Provider": prov,
        "Total Submitted": totals.get("submitted", ""),
        "Total Allowed": totals.get("allowed", ""),
        "Total Benefit": totals.get("benefit", ""),
        "Total Payment": totals.get("payment", ""),
        "Total Deductible": deductible or "",
        "Total Copay": copay or "",
        "Total Coinsurance": coinsurance or "",
        "Member Paid (Deductible+Copay+Coinsurance)": f"{member_paid}",
    }

# ------------ Patient from bundle ------------
_patient_ref_re = re.compile(r'Patient/([^/\s]+)')
def extract_patient_from_eob_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    for entry in bundle.get('entry', []):
        res = entry.get('resource', {})
        if res.get('resourceType') == 'ExplanationOfBenefit':
            ref = (((res.get('patient') or {}).get('reference')) or '')
            m = _patient_ref_re.search(ref)
            if m:
                return {'PatientID': m.group(1), 'PatientReference': ref}
    return {'PatientID': 'UNKNOWN', 'PatientReference': 'UNKNOWN'}

# ------------ String writers ------------
def to_sentences(flat: Dict[str, Any]) -> List[str]:
    # stable key order
    items = sorted(flat.items(), key=lambda kv: kv[0])
    out = []
    for k, v in items:
        s = f"{k} is {v}."
        out.append(s)
    return out

def write_eob_txt(out_path: Path, patient_hdr: Dict[str, Any], eob_summary: Dict[str, Any], flat_eob: Dict[str, Any]) -> None:
    lines = []
    # Header blocks first (nice for grep and for deterministic metadata)
    lines.append("## Patient")
    lines.extend([f"{k} is {v}." for k, v in patient_hdr.items() if v != ""])
    lines.append("")
    lines.append("## EOB Summary")
    lines.extend([f"{k} is {v}." for k, v in eob_summary.items() if v != ""])
    lines.append("")
    lines.append("## Flattened EOB")
    lines.extend(to_sentences(flat_eob))
    text = "\n".join(lines) + "\n"
    out_path.write_text(text, encoding="utf-8")

def write_jsonl_sidecar(jsonl_path: Path, patient_hdr: Dict[str, Any], eob_summary: Dict[str, Any], flat_eob: Dict[str, Any]) -> None:
    record = {
        "patient": patient_hdr,
        "eob_summary": eob_summary,
        "flat": flat_eob,
    }
    with open(jsonl_path, "a", encoding="utf-8") as w:
        w.write(json.dumps(record, ensure_ascii=False) + "\n")

# ------------ Bundle flattener ------------
def flatten_eob_bundle(bundle_file_name: str, out_dir: str) -> None:
    p = Path(bundle_file_name)
    file_stem = p.stem

    bundle = json.loads(Path(bundle_file_name).read_text(encoding="utf-8"))

    patient_hdr = extract_patient_from_eob_bundle(bundle)

    entries = bundle.get('entry', [])
    if not entries:
        raise ValueError("No entries found in the bundle.")

    os.makedirs(out_dir, exist_ok=True)

    for i, entry in enumerate(entries):
        res = entry.get('resource', {})
        if res.get('resourceType') != 'ExplanationOfBenefit':
            continue

        # derived summary first
        eob_summary = derive_eob_summary(res)
        # full flatten
        flat_eob = flatten(res)

        out_txt = Path(out_dir) / f"{file_stem}_{i}.txt"
        write_eob_txt(out_txt, patient_hdr, eob_summary, flat_eob)

        if WRITE_JSONL:
            out_jsonl = Path(out_dir) / f"{file_stem}.jsonl"
            write_jsonl_sidecar(out_jsonl, patient_hdr, eob_summary, flat_eob)

# ------------ Main ------------
def main():
    Path(FLAT_DIR).mkdir(parents=True, exist_ok=True)
    files = list(glob.glob(RAW_FHIR_GLOB))
    if not files:
        raise FileNotFoundError(f"No files matched: {RAW_FHIR_GLOB}")
    for fp in files:
        flatten_eob_bundle(fp, FLAT_DIR)
    print(f"Done. Flat files written to: {FLAT_DIR}")

if __name__ == "__main__":
    main()