import re
from decimal import Decimal, InvalidOperation
from dateutil import parser as dateparser
import pdfplumber
from django.core.files.storage import default_storage
from django.conf import settings
import os
from typing import List, Dict, Any, Optional

# --- Parsers & helpers ---
def _parse_decimal(s):
    if s is None:
        return Decimal("0")
    try:
        # remove commas, whitespace, currency signs
        cleaned = re.sub(r"[^\d\.\-]", "", str(s))
        if cleaned == "":
            return Decimal("0")
        return Decimal(cleaned)
    except (InvalidOperation, TypeError):
        return Decimal("0")

def _parse_int(s):
    try:
        return int(float(str(s)))
    except Exception:
        return 0

def _parse_date(s):
    if not s:
        return None
    try:
        return dateparser.parse(str(s), dayfirst=False).date()
    except Exception:
        return None

# --- Table extraction using pdfplumber ---
def extract_tables_from_pdf(path: str) -> List[List[List[str]]]:
    """
    Return list of tables found per page (list of rows -> row is list of cells).
    """
    tables = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            try:
                tbls = page.extract_tables()
            except Exception:
                tbls = []
            if tbls:
                for t in tbls:
                    # normalize cell strings
                    norm = [[cell.strip() if cell else "" for cell in row] for row in t]
                    tables.append(norm)
    return tables

# --- Row mapping routine (best-effort) ---
def normalize_cell(cell: str) -> str:
    return (cell or "").strip()

def guess_table_headers(table: List[List[str]]) -> Optional[Dict[str,int]]:
    """
    Given a table (list of rows), attempt to find header row and map key columns.
    Returns dict header_name -> index (e.g. 'code': 2, 'name': 3, 'qty': 4, ...)
    This is heuristic-based: checks for known header keywords.
    """
    header_keys = {
        "code": ["code", "item code", "prod code"],
        "name": ["description", "item description", "product"],
        "hsn": ["hsn", "hsn/sac"],
        "qty": ["qty", "quantity", "quantity billed", "qty billed"],
        "free_qty": ["free", "free qty"],
        "pack": ["pack", "pack size"],
        "batch": ["batch", "batch no", "batch no."],
        "mfg": ["mfg", "mfg date", "mfg. date"],
        "exp": ["exp", "expiry", "exp date"],
        "mrp": ["mrp", "new mrp", "old mrp"],
        "rate": ["rate"],
        "disc_pct": ["disc %", "discount %", "disc%"],
        "disc_amt": ["disc amt", "discount amt", "disc amount"],
        "taxable": ["taxable"],
        "cgst_pct": ["cgst %", "cgst%"],
        "cgst_amt": ["cgst amt"],
        "sgst_pct": ["sgst %", "sgst%"],
        "sgst_amt": ["sgst amt"],
        "net": ["net value", "net amt", "net"]
    }

    # look for row that looks like a header (contains header keywords)
    for i, row in enumerate(table[:4]):  # header usually in first 3 rows
        lower_cells = [normalize_cell(c).lower() for c in row]
        hits = 0
        mapping = {}
        for key, keywords in header_keys.items():
            for kw in keywords:
                if any(kw in c for c in lower_cells):
                    mapping[key] = lower_cells.index(next(c for c in lower_cells if kw in c))
                    hits += 1
                    break
        if hits >= 3:
            return mapping

    # fallback: try first row as header with fuzzy match
    lower_cells = [normalize_cell(c).lower() for c in table[0]]
    mapping = {}
    for key, keywords in header_keys.items():
        for kw in keywords:
            for idx, c in enumerate(lower_cells):
                if kw in c:
                    mapping[key] = idx
                    break
            if key in mapping:
                break
    if mapping:
        return mapping
    return None

def rows_from_table_with_header(table: List[List[str]], header_map: Dict[str,int]) -> List[Dict[str,str]]:
    """
    Convert table rows to list of dicts using header_map.
    """
    rows = []
    # find header row index by locating the row containing header_map values
    header_idx = 0
    # assume header at row 0 or 1; use header_map indices to detect
    for i in range(min(3, len(table))):
        row = [normalize_cell(c).lower() for c in table[i]]
        if any(k in row[idx] for idx in header_map.values() for k in []):
            header_idx = i
            break
    for r in table[header_idx+1:]:
        obj = {}
        for key, idx in header_map.items():
            if idx < len(r):
                obj[key] = normalize_cell(r[idx])
            else:
                obj[key] = ""
        # skip empty rows
        if any(v for v in obj.values()):
            rows.append(obj)
    return rows

def extract_purchase_items_from_pdf(path: str) -> List[Dict[str, Any]]:
    """
    Try to extract purchase items with a best-effort approach.
    Returns list of dicts with keys: product_code, name, qty, free_qty, pack, batch_no,
    mfg_date, exp_date, mrp, rate, discount_percent, discount_amount, taxable_amount, cgst_pct, cgst_amt, sgst_pct, sgst_amt, net_value
    """
    tables = extract_tables_from_pdf(path)
    if not tables:
        return []

    items = []
    # iterate tables and try to map
    for table in tables:
        header_map = guess_table_headers(table)
        if not header_map:
            continue
        rows = rows_from_table_with_header(table, header_map)
        for row in rows:
            # map to common keys
            it = {}
            it["product_code"] = row.get("code") or ""
            it["name"] = row.get("name") or ""
            it["hsn"] = row.get("hsn") or ""
            it["qty"] = _parse_decimal(row.get("qty") or row.get("quantity") or 0)
            it["free_qty"] = _parse_decimal(row.get("free_qty") or 0)
            it["pack"] = row.get("pack") or ""
            it["batch_no"] = row.get("batch") or ""
            it["mfg_date"] = _parse_date(row.get("mfg"))
            it["expiry_date"] = _parse_date(row.get("exp"))
            it["mrp"] = _parse_decimal(row.get("mrp"))
            it["rate"] = _parse_decimal(row.get("rate"))
            it["discount_percent"] = _parse_decimal(row.get("disc_pct") or 0)
            it["discount_amount"] = _parse_decimal(row.get("disc_amt") or 0)
            it["taxable_amount"] = _parse_decimal(row.get("taxable") or 0)
            it["cgst_percent"] = _parse_decimal(row.get("cgst_pct") or 0)
            it["cgst_amount"] = _parse_decimal(row.get("cgst_amt") or 0)
            it["sgst_percent"] = _parse_decimal(row.get("sgst_pct") or 0)
            it["sgst_amount"] = _parse_decimal(row.get("sgst_amt") or 0)
            it["net_value"] = _parse_decimal(row.get("net") or 0)
            items.append(it)
    return items
