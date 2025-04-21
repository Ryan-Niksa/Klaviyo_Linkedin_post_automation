from klaviyo_sdk.client import Client
import os
from dotenv import load_dotenv

load_dotenv()

client = Client(api_key=os.getenv("PRIVATE_API_KEY"))

# STEP 1: Get List ID
lists = client.lists.get_lists()
your_list_id = next(
    l["id"] for l in lists["data"] if l["attributes"]["name"] == "Your List Name"
)

# STEP 2: Create Campaign
campaign = client.campaigns.create_campaign({
    "data": {
        "type": "campaign",
        "attributes": {
            "name": "Plain Text Python Campaign",
            "channel": "email",
            "audiences": [your_list_id],
            "subject": "Hello from Python!",
            "from_email": "you@example.com",
            "from_name": "Your Name",
            "reply_to_email": "you@example.com"
        }
    }
})

campaign_id = campaign["data"]["id"]

# STEP 3: Set Inline Content (plain text as HTML body)
plain_text = "Hi there,\nThis is a plain text email sent via Klaviyo API and Python SDK.\nCheers!"
html_body = f"<pre>{plain_text}</pre>"

client.campaigns.update_campaign_content(
    campaign_id,
    {
        "data": {
            "type": "campaign_content",
            "attributes": {
                "html": html_body
            }
        }
    }
)

# STEP 4: Send Campaign
client.campaigns.send_campaign(campaign_id)