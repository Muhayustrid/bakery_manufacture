import frappe
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
	SerialandBatchBundle,
)


class BakerySerialAndBatchBundle(SerialandBatchBundle):
	def set_serial_and_batch_values(self, parent, row, qty_field=None):
		if (
			parent.doctype == "Stock Entry"
			and parent.stock_entry_type == "Manufacture"
			and self.has_batch_no
			and self.type_of_transaction == "Inward"
			and len(self.entries) == 1
		):
			old_qty = self.entries[0].qty
			new_qty = row.transfer_qty

			if old_qty != new_qty:
				self.entries[0].qty = new_qty
				self.save()

				frappe.logger("bakery_manufacturing").info(
					f"Batch qty auto-adjusted | Batch: {self.entries[0].batch_no} | "
					f"Work Order: {parent.work_order} | "
					f"Planned: {old_qty} -> Actual: {new_qty}"
				)

		super().set_serial_and_batch_values(parent, row, qty_field=qty_field)
