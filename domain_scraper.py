import os
import time
import csv
import random
import tldextract
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from fake_useragent import UserAgent

# Constants
DOMAINS_PER_BREAK = 20
BREAK_DURATION = 20
MAX_RETRIES = 5
OUTPUT_DIR = "output_domains"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ua = UserAgent()
headers = {
    "User-Agent": ua.random
}

def read_urls(file_path):
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def extract_domain_info(text):
    # Heuristic function to find domains and associated data
    ext = tldextract.extract(text)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return None

def clean_filename(url):
    parsed = urlparse(url)
    return parsed.netloc.replace('.', '_')

def smart_extract(soup):
    """
    Try to extract rows that look like domain listings.
    Looks for tables or repeating blocks.
    """
    rows = []
    tables = soup.find_all("table")
    if tables:
        for table in tables:
            for tr in table.find_all("tr"):
                row = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if any(extract_domain_info(cell) for cell in row):
                    rows.append(row)
    else:
        # fallback to divs/spans
        all_tags = soup.find_all(["div", "span", "li", "p"])
        for tag in all_tags:
            text = tag.get_text(strip=True)
            domain = extract_domain_info(text)
            if domain:
                rows.append([domain, text])
    return rows

def scrape_site(url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Fetching {url} (attempt {attempt})")
            response = requests.get(url, headers={"User-Agent": ua.random}, timeout=15)
            if response.status_code != 200:
                raise Exception(f"Status code: {response.status_code}")

            soup = BeautifulSoup(response.text, "html.parser")
            extracted_rows = smart_extract(soup)

            filename = clean_filename(url) + ".csv"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, "w", newline='', encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(extracted_rows)
            print(f"Saved {len(extracted_rows)} domains to {filepath}\n")
            return len(extracted_rows)

        except Exception as e:
            print(f"Error on {url}: {e}")
            if attempt == MAX_RETRIES:
                with open("failed_sites.log", "a") as f:
                    f.write(f"{url} failed after {MAX_RETRIES} attempts\n")
            time.sleep(5)
    return 0

def main():
    file_path = input("Enter the path to your text file with URLs: ").strip()
    if not os.path.exists(file_path):
        print("File not found.")
        return

    urls = read_urls(file_path)
    total_scraped = 0
    for idx, url in enumerate(urls, 1):
        scraped = scrape_site(url)
        total_scraped += scraped
        if idx % DOMAINS_PER_BREAK == 0:
            print(f"Reached {idx} sites. Taking a {BREAK_DURATION}s break...\n")
            time.sleep(BREAK_DURATION)

    print("\nDone. All CSVs saved in the 'output_domains' folder.")

if __name__ == "__main__":
    main()
