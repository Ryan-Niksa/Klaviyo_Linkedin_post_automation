import requests
import webbrowser
from urllib.parse import urlencode

client_id = "86xanwexeor9gj"
client_secret = "WPL_AP1.G2nIrz6xcXNzjDZX.hsPhVw=="
redirect_uri = "http://192.168.159.131:5000"

params = {
    "response_type": "code",
    "client_id": client_id,
    "redirect_uri": redirect_uri,
    "scope": "profile email openid w_member_social w_organization_social r_organization_social"
}
auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(params)
print("Opening browser for authorization...")
webbrowser.open(auth_url)