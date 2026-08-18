import unittest
from unittest.mock import patch

from bakery_manufacturing.overrides import barcode_scanner


class TestBarcodeScannerShim(unittest.TestCase):
	"""The lazy shim kept for Python importers after stock ownership moved out.

	The shim is registered in no hook and carries no ``@frappe.whitelist()``; it
	exists only so an in-process caller that still imports the old path keeps
	working. Both of its branches are covered here.
	"""

	def test_delegates_to_stock_additional(self):
		sentinel = {"item_code": "ITEM-1", "batch_no": "BATCH-1"}
		with patch(
			"stock_additional.overrides.barcode_scanner.custom_scan_barcode", return_value=sentinel
		) as implementation:
			result = barcode_scanner.custom_scan_barcode("BATCH-1", {"company": "Company"})

		implementation.assert_called_once_with("BATCH-1", {"company": "Company"})
		self.assertIs(result, sentinel)

	def test_default_ctx_is_forwarded_as_none(self):
		with patch(
			"stock_additional.overrides.barcode_scanner.custom_scan_barcode", return_value={}
		) as implementation:
			barcode_scanner.custom_scan_barcode("BATCH-1")

		implementation.assert_called_once_with("BATCH-1", None)

	def test_missing_stock_additional_raises_actionable_import_error(self):
		"""Without the owning app installed, the shim must name it in the error."""
		real_import = (
			__builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
		)

		def blocked_import(name, *args, **kwargs):
			if name.startswith("stock_additional"):
				raise ImportError(f"No module named {name!r}")
			return real_import(name, *args, **kwargs)

		with patch("builtins.__import__", side_effect=blocked_import):
			with self.assertRaises(ImportError) as raised:
				barcode_scanner.custom_scan_barcode("BATCH-1")

		# Assert the shim's own wording, not merely that "stock_additional" appears —
		# the underlying "No module named 'stock_additional'" would satisfy that too,
		# so this and the __cause__ chain are what prove the re-raise ran.
		self.assertEqual(
			str(raised.exception),
			"stock_additional is required for the legacy bakery barcode path",
		)
		self.assertIsInstance(raised.exception.__cause__, ImportError)
