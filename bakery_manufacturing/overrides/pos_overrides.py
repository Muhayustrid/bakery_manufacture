import frappe
from erpnext.selling.page.point_of_sale.point_of_sale import (
    get_invoice_filters,
    add_doctype_to_results,
    order_results_by_posting_date,
)


@frappe.whitelist()
def custom_get_past_order_list(search_term, status, limit=20):
    """Override get_past_order_list: tambah custom_walk_in_customer_name ke search + fields."""
    fields = [
        "name", "grand_total", "currency", "customer",
        "customer_name", "custom_walk_in_customer_name",
        "posting_time", "posting_date",
    ]
    invoice_list = []

    if search_term and status:
        for dt in ["POS Invoice", "Sales Invoice"]:
            by_customer = frappe.db.get_list(
                dt,
                filters=get_invoice_filters(dt, status),
                or_filters={
                    "customer_name": ["like", f"%{search_term}%"],
                    "customer": ["like", f"%{search_term}%"],
                    "custom_walk_in_customer_name": ["like", f"%{search_term}%"],
                },
                fields=fields,
                page_length=limit,
            )
            by_name = frappe.db.get_list(
                dt,
                filters=get_invoice_filters(dt, status, name=search_term),
                fields=fields,
                page_length=limit,
            )
            invoice_list.extend(add_doctype_to_results(dt, by_customer + by_name))

    elif status:
        for dt in ["POS Invoice", "Sales Invoice"]:
            result = frappe.db.get_list(
                dt,
                filters=get_invoice_filters(dt, status),
                fields=fields,
                page_length=limit,
            )
            invoice_list.extend(add_doctype_to_results(dt, result))

    return order_results_by_posting_date(invoice_list)
