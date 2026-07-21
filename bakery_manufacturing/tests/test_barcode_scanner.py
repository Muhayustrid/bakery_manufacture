import frappe
from frappe.tests.utils import FrappeTestCase

from bakery_manufacturing.overrides.barcode_scanner import custom_scan_barcode


class TestCustomScanBarcode(FrappeTestCase):
    def setUp(self):
        # `_Test Company` tidak ada di site development.localhost; pakai default company.
        self.company = frappe.db.get_single_value("Global Defaults", "default_company")

        # Pastikan UOM yang dipakai ada (Frappe default ada "Unit" & "Nos"; "Box" juga umum)
        self._ensure_uom("Gram")
        self._ensure_uom("Carton")

        self.item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": "_Test Bakery UOM Item",
                "item_name": "_Test Bakery UOM Item",
                "item_group": "All Item Groups",
                "stock_uom": "Gram",
                "has_batch_no": 1,
                "create_new_batch": 1,
                "custom_default_uom_warehouse": "Carton",
                "uoms": [
                    {"uom": "Gram", "conversion_factor": 1.0},
                    {"uom": "Carton", "conversion_factor": 1000.0},
                ],
            }
        )
        self.item.insert(ignore_permissions=True)

        self.batch = frappe.get_doc(
            {
                "doctype": "Batch",
                "batch_id": "_TEST-BATCH-UOM-001",
                "item": self.item.item_code,
            }
        )
        self.batch.insert(ignore_permissions=True)

        # Core scan_barcode caches results for 120s (frappe.local.cache + Redis).
        # FrappeTestCase only flushes cache at class teardown, not between tests,
        # so test N+1 would hit cache with item_code from test N (already deleted
        # by tearDown) → DoesNotExistError. Clear the relevant cache keys here.
        for search_value in (self.batch.name, "_TEST-BC-001"):
            frappe.cache().delete_value(f"erpnext:barcode_scan:{search_value}")

    def tearDown(self):
        frappe.delete_doc("Batch", self.batch.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Item", self.item.item_code, force=True, ignore_permissions=True)

    def test_scan_batch_returns_custom_uom(self):
        data = custom_scan_barcode(self.batch.name, ctx={"company": self.company})
        self.assertEqual(data.get("batch_no"), self.batch.name)
        self.assertEqual(data.get("item_code"), self.item.item_code)
        self.assertEqual(data.get("uom"), "Carton")
        self.assertEqual(data.get("conversion_factor"), 1000.0)

    def test_scan_batch_item_without_custom_field_returns_no_uom(self):
        # Item tanpa custom_default_uom_warehouse → jangan tambah uom
        self.item.custom_default_uom_warehouse = None
        self.item.save(ignore_permissions=True)

        data = custom_scan_barcode(self.batch.name, ctx={"company": self.company})
        self.assertEqual(data.get("batch_no"), self.batch.name)
        self.assertNotIn("uom", data)

    def test_scan_batch_custom_uom_equal_to_stock_uom_skips(self):
        # Custom field == stock_uom → tidak perlu enrich (sudah default)
        self.item.custom_default_uom_warehouse = "Gram"
        self.item.save(ignore_permissions=True)

        data = custom_scan_barcode(self.batch.name, ctx={"company": self.company})
        # Core sudah set stock_uom sebagai default row UOM via item setup,
        # enrich tidak perlu menambah uom yang sama
        self.assertNotIn("uom", data)

    def test_scan_non_batch_returns_core_data_untouched(self):
        # Barcode biasa (non-batch) → behavior core, tidak dienrich
        # Buat Item Barcode sederhana
        frappe.get_doc(
            {
                "doctype": "Item Barcode",
                "parent": self.item.item_code,
                "parenttype": "Item",
                "parentfield": "barcodes",
                "barcode": "_TEST-BC-001",
            }
        ).insert(ignore_permissions=True)

        data = custom_scan_barcode("_TEST-BC-001", ctx={"company": self.company})
        self.assertEqual(data.get("barcode"), "_TEST-BC-001")
        self.assertEqual(data.get("item_code"), self.item.item_code)
        # Core scan_barcode returns `uom` field from Item Barcode row (None if not
        # set on the barcode row). Our enrich only adds `uom` for batch scans with
        # a custom field — verify we didn't override with a real UOM.
        self.assertIsNone(data.get("uom"))

    def test_scan_batch_custom_uom_no_conversion_factor_warns(self):
        # Hapus row Carton dari tabel UOMs
        self.item.uoms = [row for row in self.item.uoms if row.uom != "Carton"]
        self.item.save(ignore_permissions=True)

        # frappe.msgprint menulis ke frappe.local.message_log
        frappe.local.message_log = []
        data = custom_scan_barcode(self.batch.name, ctx={"company": self.company})
        self.assertEqual(data.get("uom"), "Carton")
        self.assertNotIn("conversion_factor", data)
        # Pastikan ada message warning
        messages = frappe.local.message_log
        self.assertTrue(
            any(
                "conversion factor" in (m.get("message", "") if isinstance(m, dict) else str(m)).lower()
                for m in messages
            )
        )

    def _ensure_uom(self, uom_name):
        if not frappe.db.exists("UOM", uom_name):
            frappe.get_doc(
                {
                    "doctype": "UOM",
                    "uom_name": uom_name,
                    "must_be_whole_number": 0,
                }
            ).insert(ignore_permissions=True)
