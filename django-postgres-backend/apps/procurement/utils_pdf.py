import re
import os
from decimal import Decimal, InvalidOperation
from dateutil import parser as dateparser
import pdfplumber
import pytesseract
from PIL import Image

# Only set tesseract path on Windows (Azure/Linux has it in PATH)
if os.name == 'nt':  # Windows
    tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
# On Linux/Azure, tesseract should be installed and available in PATH


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def _parse_decimal(s):
    if s is None:
        return Decimal("0")
    try:
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


def extract_tables_from_pdf(path: str):
    tables = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tbls = []
            try:
                tbls = page.extract_tables()
            except Exception:
                pass

            for t in tbls:
                norm = [[(c or "").strip() for c in row] for row in t]
                tables.append(norm)
    return tables


def normalize_cell(cell: str):
    return (cell or "").strip()


def guess_table_headers(table):
    header_keywords = {
        "code": ["code", "item code", "prod code"],
        "name": ["description", "item description", "product"],
        "qty": ["qty", "quantity"],
        "pack": ["pack", "pack size"],
        "batch": ["batch", "batch no"],
        "exp": ["exp", "expiry"],
        "mrp": ["mrp"],
        "rate": ["rate"],
        "net": ["net", "net value"],
    }

    # try first 3 rows to detect header row
    for row in table[:3]:
        lower = [c.lower() for c in row]
        mapping = {}
        for key, kws in header_keywords.items():
            for kw in kws:
                for idx, col in enumerate(lower):
                    if kw in col:
                        mapping[key] = idx
                        break
                if key in mapping:
                    break
        if len(mapping) >= 3:
            return mapping

    return None


def rows_from_table_with_header(table, header_map):
    rows = []
    header_idx = 0  # assume header row = first row with mapping

    for r in table[header_idx + 1:]:
        obj = {}
        for key, idx in header_map.items():
            obj[key] = normalize_cell(r[idx]) if idx < len(r) else ""
        if any(obj.values()):
            rows.append(obj)
    return rows


# ---------------------------------------------------------
# FINAL UPDATED FUNCTION (OCR + TABLES)
# ---------------------------------------------------------
def _parse_decimal(v):
    try:
        return Decimal(str(v).strip())
    except:
        return Decimal("0")


def extract_purchase_items_from_pdf(path: str):
    """
    FINAL WORKING VERSION FOR YOUR PDF FORMAT.
    Your PDF has lines like:
        1 GLIMINEX M2 TAB 1 0
        2 NOSKURF LOTION 150ML 1 0
    Pattern:
        SNO  NAME  QTY  FREE
    """

    items = []

    # 1. Extract RAW text from PDF
    full_text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            full_text += "\n" + txt

    if not full_text.strip():
        return []

    # 2. Split lines
    lines = full_text.split("\n")

    # 3. Pattern: SNO NAME QTY FREE
    line_pattern = re.compile(
        r"^\s*(\d+)\s+([A-Za-z0-9\-\/\(\) ,]+?)\s+(\d+)\s+(\d+)\s*$"
    )

    for line in lines:
        m = line_pattern.match(line.strip())
        if m:
            sno = m.group(1)
            name = m.group(2).strip()
            qty = m.group(3)
            free = m.group(4)

            items.append({
                "product_code": "",
                "name": name,
                "qty": _parse_decimal(qty),
                "free_qty": _parse_decimal(free),
                "pack": "",
                "batch_no": "",
                "mfg_date": None,
                "expiry_date": None,
                "mrp": Decimal("0"),
                "rate": Decimal("0"),
                "discount_percent": Decimal("0"),
                "discount_amount": Decimal("0"),
                "taxable_amount": Decimal("0"),
                "cgst_percent": Decimal("0"),
                "cgst_amount": Decimal("0"),
                "sgst_percent": Decimal("0"),
                "sgst_amount": Decimal("0"),
                "net_value": Decimal("0"),
            })

    return items

