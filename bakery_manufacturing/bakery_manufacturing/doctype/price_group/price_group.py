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
        pass

    def _validate_outlets(self):
        pass

    def _set_uom(self):
        pass

    def _sync_price_list(self):
        pass

    def _sync_item_prices(self):
        pass

    def _sync_pos_profiles(self):
        pass

    def _cleanup(self):
        pass
