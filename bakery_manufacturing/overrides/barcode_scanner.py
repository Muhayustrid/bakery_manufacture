import frappe
from erpnext.stock.utils import scan_barcode as original_scan_barcode


@frappe.whitelist()
def custom_scan_barcode(search_value: str):
    data = original_scan_barcode(search_value)

    if data and data.get("batch_no"):
        uom_info = resolve_batch_uom(data.get("batch_no"))
        if uom_info:
            if uom_info.get("uom"):
                data["uom"] = uom_info["uom"]
            if uom_info.get("conversion_factor"):
                data["conversion_factor"] = uom_info["conversion_factor"]
            if uom_info.get("warning"):
                data["warning"] = uom_info["warning"]

    return data


def resolve_batch_uom(batch_no):
    # logika sama seperti resolve_batch_uom Anda yang lama —
    # tentukan UOM pengepakan (carton) berdasarkan batch/item ini
    ...