app_name = "back4app_xhttp_relay"
app_title = "Back4App XHTTP Relay"
app_publisher = "alrufaaey"
app_description = "A direct streaming HTTP/HTTPS relay compatible with Frappe Cloud."
app_email = "alrufaaey4@gmail.com"
app_license = "MIT"
app_version = "0.2.0"

# This app does not require ERPNext; it only requires the Frappe Framework.
required_apps = ["frappe"]

# Public requests are relayed directly; Frappe admin, assets, and /api routes
# are excluded inside relay_before_request().
before_request = ["back4app_xhttp_relay.api.relay_before_request"]
