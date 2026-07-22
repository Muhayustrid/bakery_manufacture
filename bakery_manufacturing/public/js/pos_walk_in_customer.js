// POS Walk-in Customer Name extension for bakery_manufacturing
// Polls for POS readiness, injects walk-in name field below Customer selector.
// Shows walk-in name in Recent Orders.

(function () {
	var current_pos = null;
	var observer = null;

	// Poll every 1s — cheap because guards prevent real work
	setInterval(function () {
		// Only on POS page
		if (frappe.get_route && frappe.get_route()[0] !== "point-of-sale") {
			current_pos = null;
			return;
		}
		if (!window.cur_pos || !cur_pos.cart || !cur_pos.cart.$customer_section) {
			return;
		}
		// New POS session detected
		if (current_pos !== cur_pos) {
			current_pos = cur_pos;
			setup();
		}
	}, 1000);

	function setup() {
		var cart = cur_pos.cart;
		var frm = cur_pos.frm;

		// Observe DOM changes in customer section
		if (observer) observer.disconnect();
		if (cart.$customer_section && cart.$customer_section[0]) {
			observer = new MutationObserver(function () {
				inject(cart, frm);
			});
			observer.observe(cart.$customer_section[0], {
				childList: true,
				subtree: true,
			});
		}

		inject(cart, frm);
		patch_past_order_list();

		// Patch reset to re-inject
		if (!cart._walk_in_patched) {
			var orig_reset = cart.reset_customer_selector.bind(cart);
			cart.reset_customer_selector = function () {
				orig_reset();
				setTimeout(function () {
					inject(cur_pos.cart, cur_pos.frm);
				}, 300);
			};
			cart._walk_in_patched = true;
		}
	}

	function inject(cart, frm) {
		if (!cart || !cart.$customer_section) return;

		// Already injected
		if (cart.$customer_section.find(".walk-in-customer-field").length) return;

		// Don't show in expanded customer info (email/phone/loyalty view)
		if (cart.$customer_section.find(".customer-fields-container").length) return;

		// Need customer selector or customer details to be visible
		var has_selector = cart.$customer_section.find(".customer-field").length > 0;
		var has_details = cart.$customer_section.find(".customer-details").length > 0;
		if (!has_selector && !has_details) return;

		var $wrap = $(
			'<div class="walk-in-customer-field" style="margin-top:8px;padding:0 15px;">' +
				'<div class="walk-in-input"></div>' +
			"</div>"
		);
		cart.$customer_section.append($wrap);

		var walk_in = frappe.ui.form.make_control({
			df: {
				label: __("Walk-in Customer"),
				fieldtype: "Data",
				placeholder: __("Walk-in customer name (optional)"),
				onchange: function () {
					if (frm) {
						frappe.model.set_value(
							frm.doc.doctype,
							frm.doc.name,
							"custom_walk_in_customer_name",
							this.value || ""
						);
					}
				},
			},
			parent: $wrap.find(".walk-in-input"),
			render_input: true,
		});

		if (frm && frm.doc.custom_walk_in_customer_name) {
			walk_in.set_value(frm.doc.custom_walk_in_customer_name);
		}

		cart._walk_in_field = walk_in;
	}

	function patch_past_order_list() {
		if (!erpnext || !erpnext.PointOfSale || !erpnext.PointOfSale.PastOrderList)
			return;
		if (erpnext.PointOfSale.PastOrderList.prototype._walk_in_patched) return;

		var orig = erpnext.PointOfSale.PastOrderList.prototype.get_invoice_html;
		erpnext.PointOfSale.PastOrderList.prototype.get_invoice_html = function (
			invoice
		) {
			var html = orig.call(this, invoice);
			if (invoice.custom_walk_in_customer_name) {
				var safe_orig = frappe.utils.escape_html(
					frappe.ellipsis(invoice.customer_name || "", 20)
				);
				var safe_new = frappe.utils.escape_html(
					frappe.ellipsis(invoice.custom_walk_in_customer_name, 20)
				);
				html = html.replace(safe_orig, safe_new);
			}
			return html;
		};
		erpnext.PointOfSale.PastOrderList.prototype._walk_in_patched = true;
	}
})();
