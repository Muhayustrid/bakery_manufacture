app_name = "bakery_manufacturing"
app_title = "Bakery Manufacturing"
app_publisher = "ITJURI"
app_description = "Override"
app_email = "ropierpnext@gmail.com"
app_license = "mit"

# Apps
# ------------------
override_doctype_class = {
    "Serial and Batch Bundle": "bakery_manufacturing.overrides.serial_batch_bundle.BakerySerialAndBatchBundle"
}

override_whitelisted_methods = {
    "erpnext.stock.utils.scan_barcode": "bakery_manufacturing.overrides.barcode_scanner.custom_scan_barcode",
    "erpnext.selling.page.point_of_sale.point_of_sale.get_past_order_list": "bakery_manufacturing.overrides.pos_overrides.custom_get_past_order_list",
}

fixtures = [
    {"dt": "Custom Field", "filters": [["fieldname", "in", ["custom_default_uom_warehouse", "custom_walk_in_customer_name"]]]},
]

after_migrate = ["bakery_manufacturing.after_migrate.after_migrate"]

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "bakery_manufacturing",
# 		"logo": "/assets/bakery_manufacturing/logo.png",
# 		"title": "Bakery Manufacturing",
# 		"route": "/bakery_manufacturing",
# 		"has_permission": "bakery_manufacturing.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/bakery_manufacturing/css/bakery_manufacturing.css"
app_include_js = "bakery_manufacturing.bundle.js"

# include js, css files in header of web template
# web_include_css = "/assets/bakery_manufacturing/css/bakery_manufacturing.css"
# web_include_js = "/assets/bakery_manufacturing/js/bakery_manufacturing.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "bakery_manufacturing/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "bakery_manufacturing/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "bakery_manufacturing.utils.jinja_methods",
# 	"filters": "bakery_manufacturing.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "bakery_manufacturing.install.before_install"
# after_install = "bakery_manufacturing.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "bakery_manufacturing.uninstall.before_uninstall"
# after_uninstall = "bakery_manufacturing.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "bakery_manufacturing.utils.before_app_install"
# after_app_install = "bakery_manufacturing.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "bakery_manufacturing.utils.before_app_uninstall"
# after_app_uninstall = "bakery_manufacturing.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "bakery_manufacturing.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "bakery_manufacturing.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"bakery_manufacturing.tasks.all"
# 	],
# 	"daily": [
# 		"bakery_manufacturing.tasks.daily"
# 	],
# 	"hourly": [
# 		"bakery_manufacturing.tasks.hourly"
# 	],
# 	"weekly": [
# 		"bakery_manufacturing.tasks.weekly"
# 	],
# 	"monthly": [
# 		"bakery_manufacturing.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "bakery_manufacturing.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "bakery_manufacturing.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "bakery_manufacturing.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "bakery_manufacturing.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["bakery_manufacturing.utils.before_request"]
# after_request = ["bakery_manufacturing.utils.after_request"]

# Job Events
# ----------
# before_job = ["bakery_manufacturing.utils.before_job"]
# after_job = ["bakery_manufacturing.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"bakery_manufacturing.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

