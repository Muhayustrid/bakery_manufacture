# CLAUDE.md

This file provides guidance to the assistant (claude.ai/code) when working with code in this repository.

## What this is

ERPNext v16 custom app for bakery/F&B manufacturing on a Frappe Cloud private bench. Owns manufacturing-specific behavior, Price Group ↔ Price List/POS Profile sync, batch default-UOM barcode enrichment, Serial and Batch Bundle quantity sync, and the legacy Desk POS walk-in display-name customization.

**Deep rules live in `AGENTS.md`** (ownership, Price Group semantics, manufacturing qty rules, deployment). Read it before non-trivial changes. This file is the short operational map.

Mobile POS APIs, OAuth, idempotency, and Android behavior belong in `roti_ropi_pos` / `POSERPNext` — not here.

## Runtime environment

| | |
|--|--|
| Host bench | `/Users/rotiropi/DockerERPNext/frappe_docker/development/frappe-bench` |
| Container | `frappe_docker_devcontainer-frappe-1` |
| Container bench | `/workspace/development/frappe-bench` |
| Site | `development.localhost` |
| App branch | `main` (README also mentions `version-16` — verify Cloud branch before deploy) |
| Repo | `https://github.com/Muhayustrid/bakery_manufacture.git` |

**`bench` is available inside the development container, not the host shell.**

Versions drift — recheck installed Frappe/ERPNext source before relying on core methods.

## Common commands

Inside container, from `/workspace/development/frappe-bench`:

```bash
# Tests (prefer --module in this v16 env; bare --test <name> historically found zero)
bench --site development.localhost run-tests --app bakery_manufacturing
bench --site development.localhost run-tests --module bakery_manufacturing.tests.test_barcode_scanner
bench --site development.localhost run-tests --module bakery_manufacturing.bakery_manufacturing.doctype.price_group.test_price_group
bench --site development.localhost run-tests --module bakery_manufacturing.bakery_manufacturing.tests.test_serial_batch_bundle

bench --site development.localhost clear-cache
bench restart
bench build --app bakery_manufacturing
bench --site development.localhost migrate
bench --site development.localhost export-fixtures --app bakery_manufacturing
```

On host, from this app root:

```bash
pre-commit run --all-files   # ruff, eslint, prettier, pyupgrade
pre-commit install
graphify update .
graphify explain "PriceGroup"
graphify path "custom_scan_barcode" "resolve_batch_uom"
```

Note: `bench execute /tmp/file.py` has failed in this Docker setup; use reviewed `bench console` input when an approved diagnostic needs it.

## Architecture

```text
bakery_manufacturing/
├── hooks.py
├── after_migrate.py              # sidebar link: Selling → Price Group
├── fixtures/custom_field.json
├── overrides/
│   ├── serial_batch_bundle.py    # BakerySerialAndBatchBundle
│   ├── barcode_scanner.py        # custom_scan_barcode + resolve_batch_uom
│   └── pos_overrides.py          # custom_get_past_order_list (walk-in name)
├── public/js/
│   ├── bakery_manufacturing.bundle.js
│   └── pos_walk_in_customer.js
├── tests/test_barcode_scanner.py
└── bakery_manufacturing/doctype/
    ├── price_group/              # syncs Price List + Item Price + POS Profiles
    ├── price_group_item/
    └── price_group_outlet/
```

`bakery_manufacturing/bakery_manufacturing/tests/test_serial_batch_bundle.py` exists but is empty — manufacturing batch-qty behavior still lacks meaningful automated coverage.

## Active hooks (source of truth: `hooks.py`)

```python
override_doctype_class = {
    "Serial and Batch Bundle": "bakery_manufacturing.overrides.serial_batch_bundle.BakerySerialAndBatchBundle",
}

override_whitelisted_methods = {
    "erpnext.stock.utils.scan_barcode":
        "bakery_manufacturing.overrides.barcode_scanner.custom_scan_barcode",
    "erpnext.selling.page.point_of_sale.point_of_sale.get_past_order_list":
        "bakery_manufacturing.overrides.pos_overrides.custom_get_past_order_list",
}

fixtures = [
    {"dt": "Custom Field", "filters": [["fieldname", "in",
        ["custom_default_uom_warehouse", "custom_walk_in_customer_name"]]]},
]

app_include_js = "bakery_manufacturing.bundle.js"
after_migrate = ["bakery_manufacturing.after_migrate.after_migrate"]
```

Resolve overrides with `frappe.override_whitelisted_method()` when code needs the effective path. Do not import another app's private override helpers.

### Custom fields in fixture

- `Item-custom_default_uom_warehouse` — Link/UOM, default sell/scan UOM when ≠ stock_uom
- `POS Invoice-custom_walk_in_customer_name` / `Sales Invoice-custom_walk_in_customer_name`

Fixture filter is fieldname-only — inspect every export diff; it can pull matching fields from any DocType.

## Core behaviors (summary — details in AGENTS.md)

**Price Group** (`PriceGroup`): validate items/outlets → on_update sync Price List, Item Prices, and linked POS Profile `selling_price_list` → on_trash cleanup. Outlets are company+warehouse pairs; warehouse must belong to company.

**Barcode scan**: wrap core `scan_barcode`; if batch+item present, set `uom` / `conversion_factor` from Item `custom_default_uom_warehouse` via UOM Conversion Detail; warn if conversion missing.

**Serial and Batch Bundle**: subclass sets serial/batch values with manufacture qty synchronization rules (greater/less/equal planned, multi-batch, scrap/by-product — see AGENTS.md).

**Desk POS walk-in**: JS bundle + past-order list override surface `custom_walk_in_customer_name`. Mobile POS must map through the public bakery/ERPNext field boundary, not private helpers.

## Ownership vs siblings

| App | Owns |
|-----|------|
| **bakery_manufacturing** (this) | Manufacturing, Price Group, batch UOM, Desk walk-in name fields |
| **roti_ropi_pos** | Mobile POS API, OAuth, idempotency, DTOs |
| **POSERPNext** | Android client |
| **erpnext / frappe** | Core — do not edit in-tree |

## Manual regression hotspots

Manufacture qty ≠ planned; partial/multi-batch/by-product/scrap; barcode scan on PO / Stock Entry / Sales Invoice / Delivery Note; Price Group rate change → Item Price + POS Profile price list; walk-in name on Desk POS past orders.

## Skills and code navigation

- Invoke the installed `frappe-app-dev` skill for Frappe/ERPNext work and load only the task-relevant references; skip it for unrelated work
- Use `codegraph_explore` first when a `.codegraph/` index exists; use it before grep, find, or manual file reads for code discovery and impact analysis
- Do not use Graphify; verify CodeGraph findings against current source and executable tests when correctness matters
- Chat: Indonesian. Repo Markdown/code/tests/commits: English
- No commit/push/Cloud deploy/migrate production without explicit user approval
- Do not delete a directory without explicit approval unless it is strictly required for an explicitly requested application objective; inspect it and state the concrete technical reason first
- Use native `EnterWorktree` for non-trivial implementation, bug fixes, refactors, and multi-file changes; edit the active checkout only for trivial documentation or configuration changes
- Do not remove a worktree without explicit user approval
