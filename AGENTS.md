# Bakery Manufacturing App Rules

Read this file before changing anything under `apps/bakery_manufacturing/`. The bench-root `AGENTS.md` applies generally; this file refines it for this app.

## Communication and Change Control

- Communicate with the user in Indonesian.
- Write repository Markdown, code comments, technical documentation, test names, and commit messages in English.
- Do not commit, push, deploy, reset, clean, stash, migrate production, or begin a later implementation phase without explicit user approval.
- Do not revert or overwrite changes you did not make. The worktree may already contain user or generated changes.
- Verify the intended diff and fresh command output before claiming completion.

## Project and Deployment Context

- This is a bakery/F&B manufacturing custom app for ERPNext v16 on a Frappe Cloud private bench.
- Repository: `https://github.com/Muhayustrid/bakery_manufacture.git`.
- The active local app branch is `main`; README and historical app metadata also mention `version-16`. Verify the Frappe Cloud branch before every deployment.
- Historical Frappe Cloud bench group: `Version 16 Signup - Cloned`.
- Historical production/staging site: `rotiropi.j.frappe.cloud`.
- Local development site: `development.localhost`.
- Development container: `frappe_docker_devcontainer-frappe-1`.
- Host bench path: `/Users/rotiropi/DockerERPNext/frappe_docker/development/frappe-bench`.
- Container bench path: `/workspace/development/frappe-bench`.
- `bench` is available inside the development container, not the host shell.
- Installed versions verified during the 2026-07 reorganization were Frappe `16.27.1`, ERPNext `16.28.0`, and `bakery_manufacturing` `0.0.1`. Recheck installed source before implementation because versions can advance.

## Ownership Boundary

`bakery_manufacturing` owns:

- manufacturing-specific behavior;
- Manufacture Stock Entry batch-quantity synchronization;
- Price Group and its Price List/POS Profile synchronization;
- the existing legacy ERPNext Desk POS walk-in display-name customization;
- the persisted `custom_walk_in_customer_name` business field (currently owned here; `selling_additional` is the target owner after the selling cutover).

`stock_additional` owns:

- batch default-UOM barcode enrichment (`erpnext.stock.utils.scan_barcode` override);
- the persisted `Item-custom_default_uom_warehouse` business field.

`roti_ropi_pos` owns:

- versioned Mobile POS backend APIs;
- OAuth enforcement and Mobile POS authorization;
- stable Mobile POS DTOs and error contracts;
- idempotency and transaction recovery;
- Mobile POS orchestration of ERPNext documents.

Boundary rules:

- Mobile POS APIs, OAuth enforcement, idempotency, transaction recovery, and Android behavior do not belong in `bakery_manufacturing`.
- Do not move bakery behavior into `roti_ropi_pos` without explicit user approval.
- Integrate with `roti_ropi_pos` through persisted ERPNext data, registered hooks, or an explicitly public contract.
- Private bakery helpers must not become undocumented dependencies of `roti_ropi_pos`.
- Mobile POS may consume `POS Profile.selling_price_list`, resolve the effective registered barcode override, and map an approved walk-in display name to `custom_walk_in_customer_name`.
- The separate Android repository is `/Users/rotiropi/DockerERPNext/POSERPNext`.

## Core and Package Rules

- Never edit files under `apps/frappe` or `apps/erpnext` directly.
- Read the installed Frappe and ERPNext source before relying on a core method, field, hook, permission, controller, DOM structure, cache behavior, or side effect.
- Use supported app mechanisms such as `override_doctype_class`, `override_whitelisted_methods`, `app_include_js`, hooks, fixtures, and app-owned DocTypes.
- Check for competing method or controller overrides before adding one. Frappe uses the last registered whitelisted-method override.
- Every new Python package directory must contain `__init__.py`.
- Two test package locations exist and must not be confused:
  - `bakery_manufacturing.tests`
  - `bakery_manufacturing.bakery_manufacturing.tests`
- Python requirement: `>=3.14`.
- Frappe compatibility: `>=16.0.0,<17.0.0`.
- Ruff target: Python 3.14; line length 110; formatter uses tabs and double quotes.
- The app has no `package.json`; JavaScript is built through the Frappe asset builder.
- `required_apps` is currently commented out even though this app imports ERPNext and depends on ERPNext DocTypes. Treat this as a known dependency-declaration gap.

## Current App Structure

```text
apps/bakery_manufacturing/
├── pyproject.toml
├── README.md
├── bakery_manufacturing/
│   ├── __init__.py
│   ├── hooks.py
│   ├── after_migrate.py
│   ├── fixtures/
│   │   └── custom_field.json
│   ├── overrides/
│   │   ├── __init__.py
│   │   ├── serial_batch_bundle.py
│   │   ├── barcode_scanner.py
│   │   └── pos_overrides.py
│   ├── public/js/
│   │   ├── bakery_manufacturing.bundle.js
│   │   └── pos_walk_in_customer.js
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_barcode_scanner_shim.py
│   └── bakery_manufacturing/
│       ├── doctype/
│       │   ├── price_group/
│       │   ├── price_group_item/
│       │   └── price_group_outlet/
│       └── tests/
│           └── test_serial_batch_bundle.py
```

`bakery_manufacturing/bakery_manufacturing/tests/test_serial_batch_bundle.py` exists but is currently empty, so the manufacturing behavior still lacks meaningful automated coverage.

## Active Hooks and Fixtures

Source: `bakery_manufacturing/hooks.py`.

### Controller Override

```python
override_doctype_class = {
    "Serial and Batch Bundle": "bakery_manufacturing.overrides.serial_batch_bundle.BakerySerialAndBatchBundle"
}
```

### Whitelisted-Method Overrides

```python
override_whitelisted_methods = {
    "erpnext.selling.page.point_of_sale.point_of_sale.get_past_order_list": "bakery_manufacturing.overrides.pos_overrides.custom_get_past_order_list",
}
```

(Note: `erpnext.stock.utils.scan_barcode` override was moved to `stock_additional`. `bakery_manufacturing` retains only an unhooked lazy import shim at `overrides/barcode_scanner.py`.)

Use `frappe.override_whitelisted_method()` when code must resolve the effective method path. Do not import an override's private helper from another app.

### Fixtures

The active `Custom Field` fixture filter uses explicit names:

- `POS Invoice-custom_walk_in_customer_name`
- `Sales Invoice-custom_walk_in_customer_name`

`bakery_manufacturing/fixtures/custom_field.json` contains:

- `POS Invoice-custom_walk_in_customer_name`: Data, label `Walk-in Customer Name`, inserted after `customer_name`;
- `Sales Invoice-custom_walk_in_customer_name`: the same walk-in display-name field for Sales Invoice.

The `Item-custom_default_uom_warehouse` custom field moved to `stock_additional`.

Keep fixture configuration as a list of dictionaries. A filter based only on `fieldname` can export matching fields from any DocType, so inspect every fixture diff before approval.

### Assets and Migration Hook

```python
app_include_js = "bakery_manufacturing.bundle.js"
after_migrate = ["bakery_manufacturing.after_migrate.after_migrate"]
```

`bakery_manufacturing/public/js/bakery_manufacturing.bundle.js` imports `./pos_walk_in_customer.js`.

## Manufacturing Batch-Quantity Synchronization

Source: `bakery_manufacturing/overrides/serial_batch_bundle.py`.

Class and method:

- `BakerySerialAndBatchBundle`
- `BakerySerialAndBatchBundle.set_serial_and_batch_values(parent, row, qty_field=None)`
- base class: ERPNext `SerialandBatchBundle`

The override considers changing the sole Serial and Batch Bundle entry quantity to `row.transfer_qty` only when all conditions are true:

- `parent.doctype == "Stock Entry"`;
- `parent.stock_entry_type == "Manufacture"`;
- `self.has_batch_no`;
- `self.type_of_transaction == "Inward"`;
- `len(self.entries) == 1`.

When the old and new quantities differ, it:

- sets `self.entries[0].qty`;
- saves the bundle;
- logs batch number, Work Order, planned quantity, and actual quantity with `frappe.logger("bakery_manufacturing")`.

After the conditional adjustment block, it always calls `super().set_serial_and_batch_values(...)`, including when the manufacturing conditions do not match or the quantity is unchanged.

The installed core method must be re-read at `erpnext/stock/doctype/serial_and_batch_bundle/serial_and_batch_bundle.py` before changing this override.

Known limitations and risks:

- multi-entry and multi-batch bundles are deliberately skipped;
- partial Manufacture Stock Entry behavior remains unverified;
- every qualifying inward batched row is eligible, not explicitly only the finished-good row;
- by-product and scrap inward rows require manual verification;
- quantity comparison uses exact numeric inequality;
- `transfer_qty` is in stock UOM;
- the automated manufacturing test module is empty;
- historical notes say this behavior was tested locally and deployed, but current executable evidence must be generated before making a fresh verification claim.

Manual manufacturing checks:

- actual quantity greater than planned;
- actual quantity less than planned;
- actual quantity equal to planned;
- partial manufacture;
- multi-batch manufacture;
- by-product/scrap inward rows;
- appropriate Over Production Allowance.

## Batch QR and Default-UOM Behavior (Extracted to `stock_additional`)

Barcode scan override and default-UOM enrichment are now owned by `stock_additional`.

Key ownership and behavioral rules:

1. `stock_additional` overrides `erpnext.stock.utils.scan_barcode`.
2. `bakery_manufacturing.overrides.barcode_scanner.custom_scan_barcode` is an unhooked lazy import shim for backward compatibility.
3. For batch scans with a custom default UOM, `stock_additional` resolves conversion factors from `UOM Conversion Detail`.
4. **Behavior Inversion**: When a custom UOM conversion factor is missing or non-positive, `stock_additional` raises `InvalidCustomUOMError` (a `frappe.ValidationError` subclass, HTTP 417) and fails closed. It does NOT warn via `msgprint` or continue.
5. The `resolve_batch_uom` function has been removed from `bakery_manufacturing`.

Test module: `bakery_manufacturing.tests.test_barcode_scanner_shim`.

## Price Group

Price Group belongs to `bakery_manufacturing`, not `roti_ropi_pos`.

Sources:

- `bakery_manufacturing/bakery_manufacturing/doctype/price_group/price_group.json`
- `bakery_manufacturing/bakery_manufacturing/doctype/price_group/price_group.py`
- `bakery_manufacturing/bakery_manufacturing/doctype/price_group/price_group.js`
- child DocTypes `Price Group Item` and `Price Group Outlet`

The `Price Group` DocType:

- autonames from `price_group_name`;
- contains `price_group_name`, `enabled`, `currency`, read-only `price_list`, `items`, and `outlets`;
- currently grants access only to `System Manager`;
- requires at least one item;
- rejects zero/negative rates and duplicate item codes;
- rejects duplicate Company/Warehouse outlets;
- verifies each Warehouse belongs to its selected Company;
- defaults a missing child-row UOM to Item `stock_uom`.

Controller: `bakery_manufacturing.bakery_manufacturing.doctype.price_group.price_group.PriceGroup`.

Controller methods:

- `validate`
- `on_update`
- `on_trash`
- `_validate_items`
- `_validate_outlets`
- `_set_uom`
- `_sync_price_list`
- `_sync_item_prices`
- `_upsert_item_price`
- `_sync_pos_profiles`
- `_cleanup`

Current synchronization behavior:

- creates a selling-only Price List named `PG-{price_group_name}`;
- updates linked Price List enabled state and currency;
- creates or updates Item Price records;
- deletes generic orphan Item Prices for removed item codes;
- finds every POS Profile with exact Company and Warehouse and updates `selling_price_list`;
- stores the first matching POS Profile in the outlet row;
- uses outlet status `Linked` or `No POS Profile`;
- warns rather than throwing when no POS Profile exists;
- on deletion, removes Item Prices and force-deletes the Price List when no other Price Group references it;
- client JavaScript filters Warehouse by Company and `is_group=0`, then clears Warehouse/POS Profile/status when Company changes.

Price Group test module:

`bakery_manufacturing.bakery_manufacturing.doctype.price_group.test_price_group`

Class: `TestPriceGroup`.

Existing methods:

- `test_save_creates_price_list_and_item_prices`
- `test_update_rate_syncs_item_price`
- `test_remove_item_deletes_item_price`
- `test_outlet_links_pos_profile`
- `test_outlet_no_pos_profile_warns_not_throws`
- `test_warehouse_wrong_company_throws`
- `test_duplicate_item_throws`

Known Price Group risks and missing coverage:

- generated Item Prices and POS Profiles have no ownership marker beyond the Price List link;
- multiple Price Groups targeting one POS Profile overwrite each other; last save wins;
- removing an outlet does not restore the previous price list;
- disabling still links profiles to the disabled Price List;
- some Item Price updates may fail when the Price List is disabled;
- `_cleanup()` can leave POS Profiles pointing at a deleted Price List;
- `_cleanup()` deletes every Item Price on that Price List, including records not necessarily generated by this controller;
- orphan cleanup can delete independent generic prices for removed items;
- Item stock-UOM changes can leave an old-UOM Item Price because orphan tracking is by item code rather than `(item_code, uom)`;
- existing Item Price currency is not explicitly refreshed when Price Group currency changes;
- tests do not cover naming collisions, multiple profiles, disable/enable, currency changes, deletion cleanup, duplicate outlets, empty items, invalid rates, or UOM changes;
- test setup may reuse/delete an existing POS Profile, commit transactions, and retain some Item/Warehouse data; review isolation before routine execution.

## Price Group Sidebar Migration

Sources and methods:

- `bakery_manufacturing/after_migrate.py`
- `bakery_manufacturing.after_migrate.after_migrate`
- `bakery_manufacturing.after_migrate._add_price_group_to_selling_sidebar`

The hook finds ERPNext's `Selling` Workspace Sidebar, skips an existing Price Group link, finds the `Items & Pricing` section, inserts a DocType link after that section's current children, and saves with ignored permissions/links.

Critical risk:

- in developer mode, `WorkspaceSidebar.before_save()` exports standard sidebar JSON;
- the current migration has indirectly modified `apps/erpnext/erpnext/workspace_sidebar/selling.json`;
- this violates the intended no-core-modification boundary even though the app did not edit that file directly;
- do not reset or discard that existing ERPNext change;
- treat the migration design and deployment state as unresolved until an approved app-safe replacement is implemented;
- the future `extend_bootinfo` approach is separate work and must not be implemented without explicit approval.

## Legacy ERPNext POS Walk-In Display Name

Server source: `bakery_manufacturing/overrides/pos_overrides.py`.

Method: `custom_get_past_order_list(search_term, status, limit=20)`.

It preserves ERPNext helpers `get_invoice_filters`, `add_doctype_to_results`, and `order_results_by_posting_date`; queries POS Invoice and POS-created Sales Invoice; includes `custom_walk_in_customer_name`; and searches that field alongside `customer` and `customer_name`.

Client source: `bakery_manufacturing/public/js/pos_walk_in_customer.js`.

Current behavior:

- the global bundle polls every second but acts only on route `point-of-sale`;
- detects `window.cur_pos`;
- injects a Data control in the customer section;
- writes `custom_walk_in_customer_name`;
- patches `ItemCart.reset_customer_selector()`;
- patches `erpnext.PointOfSale.PastOrderList.prototype.get_invoice_html()`;
- displays the custom name instead of `customer_name` in Recent Orders;
- escapes and truncates displayed values.

Known limitations:

- no server rule limits the field to the POS Profile default walk-in Customer;
- the field is available for any selected Customer;
- customer reset does not explicitly clear the custom name;
- the script depends on private globals, DOM classes, constructors, and prototype methods;
- polling remains active across Desk usage;
- server search can return duplicates and more than `limit` because each query and DocType is limited independently;
- no Python or JavaScript automated tests exist for this customization;
- fixture availability on both POS Invoice and Sales Invoice lacks integration coverage.

## Test Commands and Known Gaps

Run inside `/workspace/development/frappe-bench`:

```bash
bench --site development.localhost run-tests --module bakery_manufacturing.tests.test_barcode_scanner_shim
bench --site development.localhost run-tests --module bakery_manufacturing.bakery_manufacturing.doctype.price_group.test_price_group
bench --site development.localhost run-tests --module bakery_manufacturing.bakery_manufacturing.tests.test_serial_batch_bundle
bench --site development.localhost run-tests --app bakery_manufacturing
```

The serial/batch module currently provides no meaningful coverage because its test file is empty. In this v16 environment, use `--module`; historical `--test <name>` usage discovered zero tests.

Historical Docker operation note: `bench execute /tmp/file.py` did not work in this environment; use `bench console` with reviewed input when an approved diagnostic requires it.

Manual regression areas:

- Manufacture quantity greater/less/equal to planned;
- partial, multi-batch, by-product, and scrap manufacture;
- Purchase Order, Stock Entry, Sales Invoice, and Delivery Note barcode scan;
- normal barcode, batch QR, serial with batch, no custom UOM, stock UOM, and missing conversion;
- Price Group create/update/remove/link/warning/disable/delete/collision/multiple-profile behavior;
- default walk-in, registered Customer, Customer reset, Recent Orders statuses, display-name search, POS Invoice, and POS-created Sales Invoice.

Static checks:

```bash
cd /workspace/development/frappe-bench/apps/bakery_manufacturing
pre-commit run --all-files
```

## Build, Cache, Migration, and Fixtures

After hook changes:

```bash
bench --site development.localhost clear-cache
bench restart
```

After JavaScript changes:

```bash
bench build --app bakery_manufacturing
bench restart
```

After DocType, fixture, or migration changes:

```bash
bench --site development.localhost migrate
```

Export fixtures:

```bash
bench --site development.localhost export-fixtures --app bakery_manufacturing
```

Inspect fixture and ERPNext worktree diffs after migration. Do not allow an app migration to silently modify core source.

## Deployment Workflow

1. Run targeted tests, the full app test gate, and pre-commit locally.
2. Review bakery Git status and complete diff.
3. Review ERPNext Git status to detect indirect core-file changes.
4. Confirm the approved Frappe Cloud branch and that every site-installed app exists in the target bench.
5. Obtain explicit user approval before staging, committing, pushing, deploying, or migrating.
6. Push only the approved branch/commit.
7. Fetch the approved commit in the Frappe Cloud bench group and build/deploy the bench.
8. Update the site, run migration, and verify fixtures, DocTypes, assets, sidebar behavior, and hook resolution.
9. Repeat manufacturing, barcode, Price Group, and POS smoke checks on the deployed site.

Never claim a local commit is deployed without remote and Frappe Cloud evidence.

## Known Stale and Operational Areas

- `README.md` is still boilerplate and mentions `version-16`; it does not document current features.
- Untracked `diference.md` describes an earlier barcode-only state and is stale.
- The app-local `graphify-out/` is untracked and does not contain a complete `graph.json`.
- Branch metadata differs between the active local repository and historical app metadata; verify before deployment.
- At the time of this reorganization, the local bakery branch was ahead of `origin/main`; never infer that local behavior is available remotely or deployed without fresh Git and Frappe Cloud evidence.
- The Price Group sidebar migration can indirectly dirty ERPNext core source in developer mode.
- Do not reset, clean, or delete any of these existing files or changes without explicit approval.

## Frappe Skill and References

- Primary skill: `/Users/rotiropi/DockerERPNext/ai-skills/frappe/skills/skills/frappe-app-dev/SKILL.md`.
- This is an existing app; read `references/existing-app.md`, then load only task-relevant references.
- Before implementing APIs, hooks, DocTypes, permissions, controllers, caching, tests, or bench operations, read the corresponding `api.md`, `hooks.md`, `doctypes.md`, `permissions.md`, `controllers.md`, `caching.md`, `testing.md`, or `bench-operations.md` reference.
- For fixtures, read `hooks.md` and `bench-operations.md`; also read `permissions.md` for role/permission fixtures and `testing.md` for test data.
- Skills are guidance only. They do not override this file and do not replace verification against installed Frappe/ERPNext source and executable tests.
- Do not copy skill contents into project documentation.

## Graphify Navigation

- Graphify skill: `/Users/rotiropi/.config/opencode/skills/graphify/SKILL.md`.
- Bakery graph: `/Users/rotiropi/DockerERPNext/graphify-output/bakery_manufacturing/graphify-out/graph.json`.
- ERPNext graph: `/Users/rotiropi/DockerERPNext/graphify-output/erpnext/graphify-out/graph.json`.
- Frappe graph: `/Users/rotiropi/DockerERPNext/graphify-output/frappe/graphify-out/graph.json`.
- Frappe Docker graph: `/Users/rotiropi/DockerERPNext/frappe_docker/graphify-out/graph.json`.
- The app-local `graphify-out/` currently has no complete graph and must remain untouched in this task.
- Graphify is a navigation aid only. Installed source and executable tests are authoritative.
