import frappe
from frappe.tests.utils import FrappeTestCase

from bakery_manufacturing.bakery_manufacturing.doctype.price_group.price_group import PriceGroup


class TestPriceGroup(FrappeTestCase):
    def setUp(self):
        self._ensure_currency()
        self._ensure_warehouse()
        # Create POS Profile for test company + warehouse
        self.pos_profile = self._ensure_pos_profile()

    def tearDown(self):
        # Clean up Price Group + generated Price List + Item Prices
        if frappe.db.exists("Price Group", "Test Group A"):
            frappe.delete_doc("Price Group", "Test Group A", force=True)
        # Clean generated Price List
        if frappe.db.exists("Price List", "PG-Test Group A"):
            frappe.delete_doc("Price List", "PG-Test Group A", force=True)
        # Clean test POS Profile
        if self.pos_profile and frappe.db.exists("POS Profile", self.pos_profile):
            frappe.delete_doc("POS Profile", self.pos_profile, force=True)
        frappe.db.commit()

    def test_save_creates_price_list_and_item_prices(self):
        """Save Price Group → Price List created; Item Price rates match child."""
        item1 = self._ensure_item("_PG Test Item 1").name
        item2 = self._ensure_item("_PG Test Item 2").name
        pg = self._make_price_group(items=[
            {"item_code": item1, "rate": 15000},
            {"item_code": item2, "rate": 12000},
        ])
        pg.insert(ignore_permissions=True)

        # Price List created
        self.assertTrue(frappe.db.exists("Price List", "PG-Test Group A"))
        pl = frappe.get_doc("Price List", "PG-Test Group A")
        self.assertEqual(pl.selling, 1)
        self.assertEqual(pl.currency, "IDR")

        # Item Prices match
        ip1 = frappe.db.get_value("Item Price",
            {"item_code": item1, "price_list": "PG-Test Group A"},
            ["price_list_rate", "uom"], as_dict=True)
        self.assertIsNotNone(ip1)
        self.assertEqual(ip1.price_list_rate, 15000)

        ip2 = frappe.db.get_value("Item Price",
            {"item_code": item2, "price_list": "PG-Test Group A"},
            "price_list_rate")
        self.assertEqual(ip2, 12000)

    def test_update_rate_syncs_item_price(self):
        """Change rate → Item Price updated."""
        item1 = self._ensure_item("_PG Test Item 1").name
        pg = self._make_price_group(items=[
            {"item_code": item1, "rate": 15000},
        ])
        pg.insert(ignore_permissions=True)

        # Change rate
        pg.items[0].rate = 18000
        pg.save()

        ip_rate = frappe.db.get_value("Item Price",
            {"item_code": item1, "price_list": "PG-Test Group A"},
            "price_list_rate")
        self.assertEqual(ip_rate, 18000)

    def test_remove_item_deletes_item_price(self):
        """Remove item from child → corresponding Item Price deleted."""
        item1 = self._ensure_item("_PG Test Item 1").name
        item2 = self._ensure_item("_PG Test Item 2").name
        pg = self._make_price_group(items=[
            {"item_code": item1, "rate": 15000},
            {"item_code": item2, "rate": 12000},
        ])
        pg.insert(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("Item Price",
            {"item_code": item2, "price_list": "PG-Test Group A"}))

        # Remove item 2
        pg.items = [row for row in pg.items if row.item_code != item2]
        pg.save()

        self.assertFalse(frappe.db.exists("Item Price",
            {"item_code": item2, "price_list": "PG-Test Group A"}))
        # Item 1 still exists
        self.assertTrue(frappe.db.exists("Item Price",
            {"item_code": item1, "price_list": "PG-Test Group A"}))

    def test_outlet_links_pos_profile(self):
        """Outlet matches one POS Profile → selling_price_list set."""
        if not self.pos_profile:
            self.skipTest("POS Profile creation failed on this site — skipping outlet link test")
        company = self._get_default_company()
        warehouse = self._get_default_warehouse()
        pg = self._make_price_group(
            items=[{"item_code": self._ensure_item("_PG Test Item 1").name, "rate": 15000}],
            outlets=[{"company": company, "warehouse": warehouse}],
        )
        pg.insert(ignore_permissions=True)

        # POS Profile selling_price_list updated
        pp = frappe.get_doc("POS Profile", self.pos_profile)
        self.assertEqual(pp.selling_price_list, "PG-Test Group A")

        # Outlet row updated
        pg.reload()
        self.assertEqual(pg.outlets[0].pos_profile, self.pos_profile)
        self.assertEqual(pg.outlets[0].status, "Linked")

    def test_outlet_no_pos_profile_warns_not_throws(self):
        """Outlet with no POS Profile → no throw; status No POS Profile."""
        company = self._get_default_company()
        # Use a warehouse that has no POS Profile
        fake_wh = self._ensure_warehouse("_PG No POS WH", company)

        pg = self._make_price_group(
            items=[{"item_code": self._ensure_item("_PG Test Item 1").name, "rate": 15000}],
            outlets=[{"company": company, "warehouse": fake_wh}],
        )
        # Should NOT throw
        pg.insert(ignore_permissions=True)

        pg.reload()
        self.assertEqual(pg.outlets[0].status, "No POS Profile")
        self.assertFalse(pg.outlets[0].pos_profile)

    def test_warehouse_wrong_company_throws(self):
        """Warehouse not belonging to company → throw."""
        company = self._get_default_company()
        # Create warehouse under a DIFFERENT company
        other_company = self._ensure_company("_PG Other Co")
        other_wh = self._ensure_warehouse("_PG Other WH", other_company)

        pg = self._make_price_group(
            items=[{"item_code": self._ensure_item("_PG Test Item 1").name, "rate": 15000}],
            outlets=[{"company": company, "warehouse": other_wh}],
        )

        with self.assertRaises(frappe.ValidationError):
            pg.insert(ignore_permissions=True)

        # Cleanup
        frappe.delete_doc("Warehouse", other_wh, force=True)
        frappe.delete_doc("Company", other_company, force=True)

    def test_duplicate_item_throws(self):
        """Duplicate item_code in child → throw."""
        item = self._ensure_item("_PG Test Item 1").name
        pg = self._make_price_group(items=[
            {"item_code": item, "rate": 15000},
            {"item_code": item, "rate": 12000},
        ])

        with self.assertRaises(frappe.ValidationError):
            pg.insert(ignore_permissions=True)

    # --- helpers ---

    def _make_price_group(self, items, outlets=None):
        return frappe.get_doc({
            "doctype": "Price Group",
            "price_group_name": "Test Group A",
            "currency": "IDR",
            "enabled": 1,
            "items": items,
            "outlets": outlets or [],
        })

    def _get_default_company(self):
        return frappe.db.get_single_value("Global Defaults", "default_company")

    def _get_default_warehouse(self):
        # Get warehouse from POS Profile we created
        if self.pos_profile:
            return frappe.db.get_value("POS Profile", self.pos_profile, "warehouse")
        # Fallback: any warehouse for default company
        company = self._get_default_company()
        return frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")

    def _ensure_currency(self):
        if not frappe.db.exists("Currency", "IDR"):
            frappe.get_doc({
                "doctype": "Currency", "currency_name": "IDR",
                "enabled": 1, "fraction": "Sen", "fraction_units": 100,
                "symbol": "Rp", "smallest_currency_fraction_value": 100,
            }).insert(ignore_permissions=True)

    def _ensure_warehouse(self, name=None, company=None):
        wh_name = name or "_PG Test WH"
        if frappe.db.exists("Warehouse", {"warehouse_name": wh_name, "company": company or self._get_default_company()}):
            return frappe.db.get_value("Warehouse", {"warehouse_name": wh_name, "company": company or self._get_default_company()}, "name")
        wh = frappe.get_doc({
            "doctype": "Warehouse",
            "warehouse_name": wh_name,
            "company": company or self._get_default_company(),
            "is_group": 0,
        })
        wh.insert(ignore_permissions=True)
        return wh.name

    def _ensure_item(self, item_code):
        if frappe.db.exists("Item", item_code):
            return frappe.get_doc("Item", item_code)
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_code,
            "item_group": "All Item Groups",
            "stock_uom": "Unit",
            "is_stock_item": 1,
        })
        item.insert(ignore_permissions=True)
        return item

    def _ensure_company(self, company_name):
        if frappe.db.exists("Company", company_name):
            return company_name
        co = frappe.get_doc({
            "doctype": "Company",
            "company_name": company_name,
            "default_currency": "IDR",
            "country": "Indonesia",
        })
        co.insert(ignore_permissions=True)
        return co.name

    def _ensure_pos_profile(self):
        try:
            company = self._get_default_company()
            warehouse = self._ensure_warehouse("_PG Test WH", company)
            # Check if POS Profile already exists for this company+warehouse
            existing = frappe.db.get_value("POS Profile",
                {"company": company, "warehouse": warehouse}, "name")
            if existing:
                return existing
            # Resolve required fields — fall back gracefully if missing
            write_off_account = frappe.db.get_value("Account",
                {"company": company, "account_type": "Write Off", "is_group": 0}, "name")
            write_off_cost_center = frappe.db.get_value("Cost Center",
                {"company": company, "is_group": 0}, "name")
            selling_price_list = (
                frappe.db.get_single_value("Selling Settings", "selling_price_list")
                or "Standard Selling"
            )
            if not write_off_account or not write_off_cost_center:
                # Can't create POS Profile without these; tests that need it will skip
                return None
            pp = frappe.get_doc({
                "doctype": "POS Profile",
                "name": "_PG Test POS Profile",
                "company": company,
                "warehouse": warehouse,
                "selling_price_list": selling_price_list,
                "currency": frappe.db.get_value("Company", company, "default_currency") or "IDR",
                "write_off_account": write_off_account,
                "write_off_cost_center": write_off_cost_center,
            })
            pp.insert(ignore_permissions=True)
            return pp.name
        except Exception as e:
            frappe.logger("bakery_manufacturing").warning(
                f"_ensure_pos_profile: could not create POS Profile — {e}"
            )
            return None
