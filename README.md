### Bakery Manufacturing

Override

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app bakery_manufacturing
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/bakery_manufacturing
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### Deprecated

`bakery_manufacturing.overrides.barcode_scanner.custom_scan_barcode` is a compatibility shim
for one release. Barcode scanning and the `Item-custom_default_uom_warehouse` custom field
belong to `stock_additional`. Update legacy callers to import from `stock_additional`.

`bakery_manufacturing.overrides.pos_overrides.custom_get_past_order_list` is a compatibility
shim for one release. Price Group (with its DocTypes, controller, and generated Price List
management), the walk-in customer fields and Desk asset, and the POS past-order override
belong to `selling_additional`. Update legacy callers to import from `selling_additional`.

### License

mit
# bakery_manufacture
