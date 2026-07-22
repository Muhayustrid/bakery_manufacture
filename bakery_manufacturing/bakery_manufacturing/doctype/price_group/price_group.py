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
        pl_name = f"PG-{self.price_group_name}"

        if self.price_list and frappe.db.exists("Price List", self.price_list):
            # Update existing
            pl = frappe.get_doc("Price List", self.price_list)
            changed = False
            if pl.enabled != self.enabled:
                pl.enabled = self.enabled
                changed = True
            if pl.currency != self.currency:
                pl.currency = self.currency
                changed = True
            if changed:
                pl.save(ignore_permissions=True)
        else:
            # Check collision: PL with this name exists but belongs to something else
            if frappe.db.exists("Price List", pl_name):
                frappe.throw(
                    _("Price List {0} already exists and is not linked to this Price Group").format(
                        pl_name
                    )
                )

            # Create
            pl = frappe.get_doc({
                "doctype": "Price List",
                "price_list_name": pl_name,
                "selling": 1,
                "buying": 0,
                "currency": self.currency,
                "enabled": self.enabled,
            })
            pl.insert(ignore_permissions=True)

            self.db_set("price_list", pl.name, update_modified=False)
            self.price_list = pl.name

    def _sync_item_prices(self):
        if not self.price_list:
            return

        target_items = set()
        for row in self.items:
            target_items.add(row.item_code)
            self._upsert_item_price(row.item_code, row.uom, row.rate)

        # Delete orphaned Item Prices (item removed from child)
        existing = frappe.get_all(
            "Item Price",
            filters={
                "price_list": self.price_list,
                "customer": ("is", "not set"),
                "supplier": ("is", "not set"),
            },
            fields=["name", "item_code"],
        )
        for ip in existing:
            if ip.item_code not in target_items:
                frappe.delete_doc("Item Price", ip.name, force=True)

    def _upsert_item_price(self, item_code, uom, rate):
        existing = frappe.db.get_value(
            "Item Price",
            {
                "item_code": item_code,
                "price_list": self.price_list,
                "uom": uom,
            },
            "name",
        )

        if existing:
            ip = frappe.get_doc("Item Price", existing)
            if ip.price_list_rate != rate:
                ip.price_list_rate = rate
                ip.save(ignore_permissions=True)
        else:
            ip = frappe.get_doc({
                "doctype": "Item Price",
                "item_code": item_code,
                "uom": uom,
                "price_list": self.price_list,
                "price_list_rate": rate,
                "currency": self.currency,
            })
            ip.insert(ignore_permissions=True)

    def _sync_pos_profiles(self):
        if not self.price_list:
            return

        warnings = []
        for row in self.outlets:
            profiles = frappe.get_all(
                "POS Profile",
                filters={"company": row.company, "warehouse": row.warehouse},
                pluck="name",
            )

            if not profiles:
                row.status = "No POS Profile"
                row.pos_profile = None
                # Persist directly to avoid re-triggering on_update (infinite recursion)
                if row.name:
                    frappe.db.set_value(
                        "Price Group Outlet", row.name,
                        {"status": "No POS Profile", "pos_profile": None},
                        update_modified=False,
                    )
                warnings.append(
                    _("No POS Profile found for {0} / {1}").format(
                        row.company, row.warehouse
                    )
                )
                continue

            # Update all matching POS Profiles
            for pp_name in profiles:
                pp = frappe.get_doc("POS Profile", pp_name)
                if pp.selling_price_list != self.price_list:
                    pp.selling_price_list = self.price_list
                    pp.save(ignore_permissions=True)

            row.pos_profile = profiles[0]
            row.status = "Linked"
            # Persist directly to avoid re-triggering on_update (infinite recursion)
            if row.name:
                frappe.db.set_value(
                    "Price Group Outlet", row.name,
                    {"status": "Linked", "pos_profile": profiles[0]},
                    update_modified=False,
                )

            if len(profiles) > 1:
                frappe.msgprint(
                    _("{0} POS Profiles updated for {1} / {2}").format(
                        len(profiles), row.company, row.warehouse
                    ),
                    indicator="blue",
                    alert=True,
                )

        if warnings:
            for w in warnings:
                frappe.msgprint(w, indicator="orange", title=_("POS Profile Warning"))

    def _cleanup(self):
        if not self.price_list:
            return

        # Delete all Item Prices for this Price List
        ips = frappe.get_all(
            "Item Price",
            filters={"price_list": self.price_list},
            pluck="name",
        )
        for ip_name in ips:
            frappe.delete_doc("Item Price", ip_name, force=True)

        # Disable or delete Price List if exclusive to this group
        other_groups = frappe.db.count(
            "Price Group",
            {"price_list": self.price_list, "name": ("!=", self.name)},
        )
        if other_groups == 0:
            frappe.delete_doc("Price List", self.price_list, force=True)
