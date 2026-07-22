import frappe


def after_migrate():
    """Tambah link Price Group ke sidebar Selling → section Items & Pricing."""
    _add_price_group_to_selling_sidebar()


def _add_price_group_to_selling_sidebar():
    # Cari sidebar "Selling" dari DB
    sidebar_name = frappe.db.get_value(
        "Workspace Sidebar",
        {"title": "Selling", "app": "erpnext"},
        "name",
    )
    if not sidebar_name:
        frappe.logger("bakery_manufacturing").info(
            "Selling sidebar not found, skipping Price Group link injection"
        )
        return

    sidebar = frappe.get_doc("Workspace Sidebar", sidebar_name)

    # Cek apakah Price Group link sudah ada
    for item in sidebar.items:
        if item.link_to == "Price Group" and item.link_type == "DocType":
            return  # sudah ada, skip

    # Cari section "Items & Pricing" (type=Section Break, label=Items & Pricing)
    items_pricing_idx = None
    for i, item in enumerate(sidebar.items):
        if item.type == "Section Break" and item.label == "Items & Pricing":
            items_pricing_idx = i
            break

    if items_pricing_idx is None:
        frappe.logger("bakery_manufacturing").info(
            "Items & Pricing section not found in Selling sidebar, skipping"
        )
        return

    # Cari posisi insert: setelah link terakhir di section "Items & Pricing"
    # (sebelum section break berikutnya)
    insert_idx = items_pricing_idx + 1
    for i in range(items_pricing_idx + 1, len(sidebar.items)):
        if sidebar.items[i].child == 1:
            insert_idx = i + 1
        else:
            break

    # Insert Price Group link menggunakan append + reorder
    sidebar.append("items", {
        "child": 1,
        "collapsible": 1,
        "icon": "",
        "indent": 0,
        "keep_closed": 0,
        "label": "Price Group",
        "link_to": "Price Group",
        "link_type": "DocType",
        "show_arrow": 0,
        "type": "Link",
    })

    # Pindahkan item baru ke posisi yang benar (setelah item terakhir di section)
    # append() selalu taruh di akhir, jadi kita perlu reorder
    last_item = sidebar.items[-1]
    sidebar.items.pop()  # remove dari akhir
    sidebar.items.insert(insert_idx, last_item)  # insert di posisi yang benar

    # Update idx
    for i, item in enumerate(sidebar.items):
        item.idx = i

    sidebar.flags.ignore_permissions = True
    sidebar.flags.ignore_links = True
    sidebar.save()

    frappe.logger("bakery_manufacturing").info(
        "Added Price Group link to Selling sidebar → Items & Pricing"
    )
