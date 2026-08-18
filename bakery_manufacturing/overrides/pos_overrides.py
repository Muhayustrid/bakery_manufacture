"""Lazy compatibility shim for the moved past-order override.

The real implementation moved to
``selling_additional.overrides.pos_overrides.custom_get_past_order_list`` and this app
no longer registers any hook for it. The shim exists for one release so stale dotted
references keep working, registers nothing, and is not whitelisted — the effective
provider is selected by hook registration, which lives only in selling_additional now.
"""


def custom_get_past_order_list(search_term, status, limit=20):
	from selling_additional.overrides.pos_overrides import custom_get_past_order_list

	return custom_get_past_order_list(search_term, status, limit=limit)
