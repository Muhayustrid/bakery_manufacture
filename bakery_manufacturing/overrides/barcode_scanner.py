import frappe
from frappe import _
from erpnext.stock.utils import scan_barcode as original_scan_barcode


@frappe.whitelist()
def custom_scan_barcode(search_value: str, ctx: dict | str | None = None):
    data = original_scan_barcode(search_value, ctx)

    if data and data.get("batch_no") and data.get("item_code"):
        uom_info = resolve_batch_uom(data.get("item_code"))
        if uom_info:
            if uom_info.get("uom"):
                data["uom"] = uom_info["uom"]
            if uom_info.get("conversion_factor"):
                data["conversion_factor"] = uom_info["conversion_factor"]
            if uom_info.get("warning"):
                frappe.msgprint(uom_info["warning"], title=_("UOM Warning"), indicator="orange")

    return data


def resolve_batch_uom(item_code: str) -> dict:
    """Resolve target UOM untuk item berdasarkan custom field
    `custom_default_uom_warehouse` di Item Master.

    Return dict dengan keys:
      - uom (str|None): UOM target kalau berbeda dari stock_uom.
      - conversion_factor (float|None): conversion factor dari UOM Conversion Detail.
      - warning (str|None): pesan warning kalau conversion factor belum didefinisikan.
    """
    custom_uom = frappe.get_cached_value("Item", item_code, "custom_default_uom_warehouse")
    if not custom_uom:
        return {}

    stock_uom = frappe.get_cached_value("Item", item_code, "stock_uom")
    if custom_uom == stock_uom:
        # Tidak perlu enrich — core sudah pakai stock_uom sebagai default.
        return {}

    conversion_factor = frappe.db.get_value(
        "UOM Conversion Detail",
        {"parent": item_code, "parenttype": "Item", "uom": custom_uom},
        "conversion_factor",
    )

    result = {"uom": custom_uom}

    if conversion_factor:
        result["conversion_factor"] = float(conversion_factor)
    else:
        result["warning"] = _(
            "Item {0} punya Default UOM {1} tapi conversion factor belum didefinisikan "
            "di tabel UOMs. Qty mungkin tidak terkonversi dengan benar."
        ).format(item_code, custom_uom)

    return result
