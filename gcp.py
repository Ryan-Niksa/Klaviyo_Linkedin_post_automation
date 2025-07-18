from flask import Flask, jsonify, request
import os
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time
from dotenv import load_dotenv
import io
from PyPDF2 import PdfReader
from openai import OpenAI
from requests.auth import HTTPBasicAuth
import json

WP_BASE_URL = "https://patentlawprofessor.com/wp-json/wp/v2"

app = Flask(__name__)

DELAY_SHORT = 2
DELAY_LONG = 3

load_dotenv()

USERNAME = "admin_a683wnr3"
APPLICATION_PASSWORD = "SQ6E zz6O FbLX mGHA bBnT gHG1"

client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

WEBHOOK_URL = "http://127.0.0.1:5678/webhook/automate"

all_tags = []

def download_pdf_from_url(pdf_url):
    response = requests.get(pdf_url)
    response.raise_for_status()
    return response.content

def extract_text_from_pdf(pdf_bytes):
    pdf_stream = io.BytesIO(pdf_bytes)
    reader = PdfReader(pdf_stream)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text.strip()

def get_all_tags(site_url: str):
    tags = []
    page = 1
    while True:
        url = f"{site_url.rstrip('/')}/wp-json/wp/v2/tags?per_page=100&page={page}"
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Failed to fetch tags: {response.status_code}")
            break
        data = response.json()
        if not data:
            break
        tags.extend(tag['name'] for tag in data)
        page += 1
    return tags

def generate_article_from_text(pdf_text, allowed_tags):
    tags_string = ", ".join(allowed_tags)
    prompt = f"""
Use the following PDF content to write the article:

Your article should include the following fields:

1. Title: A clear, engaging blog post title.
2. Content: 
    <h2>Introduction</h2>
    <p>Some text...</p>
    <h2>Details</h2>
    <p>More text...</p>
3. Tags: Choose relevant tags from this list: [{tags_string}]    

pdf_content:
{pdf_text}

Generate answer as just JSON string with keys: title, content, tags
tags should be list
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an article generator from a text content assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=1800
    )
    return response.choices[0].message.content

def generate_post_from_pdf_url(pdf_url):
    pdf_bytes = download_pdf_from_url(pdf_url)
    pdf_text = extract_text_from_pdf(pdf_bytes)
    valid_tags = all_tags
    generated_post = generate_article_from_text(pdf_text, valid_tags)
    return generated_post

def get_or_create_tag(tag_name):
    response = requests.get(f"{WP_BASE_URL}/tags", params={"search": tag_name}, auth=HTTPBasicAuth(USERNAME, APPLICATION_PASSWORD))
    response.raise_for_status()
    results = response.json()
    if results:
        return results[0]["id"]
    response = requests.post(
        f"{WP_BASE_URL}/tags",
        json={"name": tag_name},
        auth=HTTPBasicAuth(USERNAME, APPLICATION_PASSWORD)
    )
    response.raise_for_status()
    return response.json()["id"]

def post_to_wordpress(title, content, tags):
    tag_ids = [get_or_create_tag(tag) for tag in tags]
    print(tag_ids)
    print(tags)
    print(all_tags)
    post_data = {
        "title": title,
        "content": content,
        "status": "publish",
        "tags": tag_ids
    }
    response = requests.post(
        f"{WP_BASE_URL}/posts",
        json=post_data,
        auth=HTTPBasicAuth(USERNAME, APPLICATION_PASSWORD)
    )
    response.raise_for_status()
    return response.json()

class USCCourtScraper:
    def __init__(self, target_date):
        self.url = 'https://www.cafc.uscourts.gov/home/case-information/opinions-orders/'
        self.driver = self._initialize_driver()
        self.all_pdf_links = []
        self.target_date = target_date

    def _initialize_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    def open_website(self):
        self.driver.get(self.url)
        time.sleep(DELAY_LONG)

    def filter_with_origin_and_current_date(self):
        try:
            date_field = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "table_1_range_from_0")))
            date_field.clear()
            date_field.send_keys(self.target_date)
            date_field.send_keys(Keys.RETURN)

            to_date_field = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "table_1_range_to_0")))
            to_date_field.clear()
            to_date_field.send_keys(self.target_date)
            to_date_field.send_keys(Keys.RETURN)

            origin_xpath = '//*[@id="table_1_2_filter"]/span/div/button'
            select_origin_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, origin_xpath)))
            select_origin_button.click()

            for li_index in [9, 15, 21]:
                option = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, f'//*[@id="table_1_2_filter"]/span/div/div/ul/li[{li_index}]/a'))
                )
                option.click()

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(DELAY_LONG)
        except Exception as e:
            print(f"Error filtering data: {e}")

    def extract_pdf_links(self):
        try:
            table_body = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "tbody")))
            rows = table_body.find_elements(By.TAG_NAME, "tr")

            origins, case_names, pdf_links, statuses, release_dates, appeal_numbers = [], [], [], [], [], []

            for row in rows:
                try:
                    td_element = row.find_elements(By.TAG_NAME, "td")
                    origin = td_element[-3].text
                    appeal_number = td_element[-4].text
                    release_date = td_element[-5].text
                    case_name = td_element[-2].find_element(By.TAG_NAME, "a").text
                    pdf_link = td_element[-2].find_element(By.TAG_NAME, "a").get_attribute("href")
                    status = td_element[-1].text
                    origins.append(origin)
                    case_names.append(case_name)
                    pdf_links.append(pdf_link)
                    statuses.append(status)
                    appeal_numbers.append(appeal_number)
                    release_dates.append(release_date)
                except Exception:
                    continue

            return {
                "origins": origins,
                "case_names": case_names,
                "pdf_links": pdf_links,
                "statuses": statuses,
                "release_dates": release_dates,
                "appeal_numbers": appeal_numbers
            }
        except Exception as e:
            print(f"Error extracting PDF links: {e}")
            return {}

    def paginate_and_scrape(self):
        all_data = {
            "origins": [],
            "case_names": [],
            "pdf_links": [],
            "statuses": [],
            "release_dates": [],
            "appeal_numbers": []
        }
        while True:
            page_data = self.extract_pdf_links()
            if not page_data["pdf_links"]:
                break
            for key in all_data:
                all_data[key].extend(page_data[key])
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                next_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="table_1_next"]')))
                next_button.click()
                time.sleep(DELAY_LONG)
            except Exception:
                print("No more pages.")
                break
        return all_data

    def run(self):
        self.open_website()
        self.filter_with_origin_and_current_date()
        time.sleep(DELAY_LONG)
        results = self.paginate_and_scrape()
        self.driver.quit()
        return results

def send_results(results):
    if not results["pdf_links"]:
        return {"message": "No new PDFs found."}

    success_count = 0
    failed_urls = []

    for id, file_url in enumerate(results["pdf_links"]):
        payload = {"file_url": file_url}
        try:
            post = generate_post_from_pdf_url(file_url)
            match = re.search(r'\{.*\}', post, re.DOTALL)
            json_str = match.group(0)
            data = json.loads(json_str)
            title = data['title']
            content = data['content']
            tags = data['tags']
            res = post_to_wordpress(title, content, tags)
            print(res['link'])
            success_count += 1
        except requests.exceptions.RequestException as e:
            print(f"Request error: {file_url}, Error: {e}")
            failed_urls.append(file_url)

    return {
        "message": f"Scraper completed! {success_count} PDFs sent successfully.",
        "failed_urls": failed_urls,
        "results": results
    }

@app.route("/run-scraper", methods=["POST"])
def run_scraper():
    data = request.get_json()
    global all_tags
    all_tags = get_all_tags("https://patentlawprofessor.com")
    target_date = data.get("date", datetime.now().strftime("%m/%d/%Y"))
    print(target_date)
    scraper = USCCourtScraper(target_date)
    results = scraper.run()
    response = send_results(results)
    return jsonify(response)

client_id = "86xanwexeor9gj"
client_secret = "WPL_AP1.G2nIrz6xcXNzjDZX.hsPhVw=="

@app.route("/", methods=["GET"])
def handle_code():
    auth_code = request.args.get("code")
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    token_data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": "http://192.168.159.131:5000",
        "client_id": client_id,
        "client_secret": client_secret
    }
    token_resp = requests.post(token_url, data=token_data)
    access_token = token_resp.json().get("access_token")
    print("Access Token:", access_token)

    headers = {"Authorization": f"Bearer {access_token}"}
    company_urn = "urn:li:organization:106499315"

    post_url = "https://api.linkedin.com/v2/ugcPosts"
    headers.update({"X-Restli-Protocol-Version": "2.0.0"})

    post_data = {
        "author": company_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": "Read our latest insights!"},
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "status": "READY",
                    "description": {"text": "Article summary"},
                    "originalUrl": "https://example.com/article",
                    "title": {"text": "First post via Linkedin API using Company account"}
                }]
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }

    response = requests.post(post_url, headers=headers, json=post_data)
    if response.status_code == 201:
        return "success"
    else:
        return "error"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
