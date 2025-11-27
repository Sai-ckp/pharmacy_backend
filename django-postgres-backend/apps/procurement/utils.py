import pdfplumber

def extract_purchase_items_from_pdf(file_path):
    items = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            for row in table:
                # Skip header rows
                if "Item Description" in row[1]:
                    continue

                try:
                    code = row[1]
                    name = row[2]
                    qty = row[5]
                    pack = row[6]
                    batch = row[7]
                    expiry = row[9]
                    mrp = row[10]
                    cost = row[12]
                    net = row[15]

                    items.append({
                        "product_code": code,
                        "name": name,
                        "qty": float(qty or 0),
                        "pack": pack,
                        "batch_no": batch,
                        "expiry": expiry,
                        "mrp": float(mrp or 0),
                        "cost": float(cost or 0),
                        "net_value": float(net or 0),
                    })

                except:
                    continue

    return items
