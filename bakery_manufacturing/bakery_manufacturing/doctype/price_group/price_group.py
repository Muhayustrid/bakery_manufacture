import frappe
from frappe import _
from frappe.model.document import Document

class PriceGroup(Document):
    def validate(self):
        self._validate_items()
        self._validate_outlets()
        self._set_uom()

    def on_update(self):
        self._sync_price_list()
        self._sync_item_prices()
        self._sync_pos_profiles()

    def on_trash(self):
        self._cleanup()

    def _validate_items(self):
        if not self.items:
            frappe.throw(_("At least one item is required"))

        seen = set()
        for row in self.items:
            if not row.rate or row.rate <= 0:
                frappe.throw(
                    _("Row {0}: Rate must be greater than zero").format(row.idx)
                )
            if row.item_code in seen:
                frappe.throw(
                    _("Row {0}: Duplicate item {1}").format(row.idx, row.item_code)
                )
            seen.add(row.item_code)

    def _validate_outlets(self):
        seen = set()
        for row in self.outlets:
            key = (row.company, row.warehouse)
            if key in seen:
                frappe.throw(
                    _("Row {0}: Duplicate outlet {1} / {2}").format(
                        row.idx, row.company, row.warehouse
                    )
                )
            seen.add(key)

            # Verify warehouse belongs to company
            wh_company = frappe.db.get_value(
                "Warehouse", row.warehouse, "company"
            )
            if wh_company != row.company:
                frappe.throw(
                    _("Row {0}: Warehouse {1} belongs to company {2}, not {3}").format(
                        row.idx, row.warehouse, wh_company, row.company
                    )
                )

    def _set_uom(self):
        for row in self.items:
            if not row.uom:
                row.uom = frappe.db.get_value(
                    "Item", row.item_code, "stock_uom"
                )

    def _sync_price_list(self):
        pass

    def _sync_item_prices(self):
        pass

    def _sync_pos_profiles(self):
        pass

    def _cleanup(self):
        pass
