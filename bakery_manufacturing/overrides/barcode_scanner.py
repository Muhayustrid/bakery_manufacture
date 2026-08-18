def custom_scan_barcode(search_value: str, ctx: dict | str | None = None):
	try:
		from stock_additional.overrides.barcode_scanner import (
			custom_scan_barcode as implementation,
		)
	except ImportError as error:
		raise ImportError("stock_additional is required for the legacy bakery barcode path") from error

	return implementation(search_value, ctx)
