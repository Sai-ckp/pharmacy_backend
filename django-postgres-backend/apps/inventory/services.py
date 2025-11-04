"""
Inventory Ledger contract (docstring only for Day 1):

Signature to implement (Day 2):

def write_movement(location_id, batch_lot_id, qty_change_base, reason, ref_doc_type, ref_doc_id):
    """Append an inventory movement to the ledger.
    - location_id: where the stock movement occurs
    - batch_lot_id: which batch lot is affected
    - qty_change_base: signed quantity delta in base units
    - reason: one of PURCHASE, SALE, TRANSFER_OUT, TRANSFER_IN, RETURN_VENDOR, WRITE_OFF, RECALL_BLOCK, ADJUSTMENT
    - ref_doc_type: reference doc type (e.g., PO, SO, ADJ)
    - ref_doc_id: external reference id
    Returns: movement_id or persisted entity
    """

Reasons (enum values expected):
- PURCHASE
- SALE
- TRANSFER_OUT
- TRANSFER_IN
- RETURN_VENDOR
- WRITE_OFF
- RECALL_BLOCK
- ADJUSTMENT

Also planned reader for validations:

def stock_on_hand(location_id, batch_lot_id) -> int:
    """Return current on-hand quantity in base units for a location/batch."""

"""

