import asyncio
import csv
import os
import re
import time
import logging
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logging.basicConfig(level=logging.INFO)

MAX_RETRIES = 5
PAUSE_EVERY = 20
PAUSE_DURATION = 20  # seconds

# Utilities
def get_site_name(url):
    parsed = urlparse(url if url.startswith("http") else "https://" + url)
    return parsed.netloc.replace("www.", "").replace(".", "_")

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

async def extract_domains_from_site(page, url):
    domains_data = []

    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_load_state("load")

        # Check for redirect or error message
        content = await page.content()
        if "domain" not in content.lower():
            logging.warning(f"No domain-related content detected on {url}. Attempting deep search...")

        # Auto-discover all clickable pagination and follow
        visited = set()
        queue = [url]

        while queue:
            current_url = queue.pop(0)
            if current_url in visited:
                continue

            visited.add(current_url)
            try:
                await page.goto(current_url, timeout=60000)
                await page.wait_for_load_state("load")
                logging.info(f"Parsing: {current_url}")
                content = await page.content()
            except PlaywrightTimeout:
                logging.error(f"Timeout on {current_url}")
                continue

            # Extract domain rows
            domain_rows = await page.locator("text=/.*\\..*/").all_inner_texts()
            for row in domain_rows:
                if not re.search(r"\.\w{2,}", row):  # crude domain match
                    continue
                domains_data.append({"Domain": row})

            # Discover next page links
            links = await page.locator("a").all()
            for link in links:
                try:
                    href = await link.get_attribute("href")
                    if href and ("page" in href or "next" in href.lower()):
                        full_url = page.url.rsplit("/", 1)[0] + "/" + href if not href.startswith("http") else href
                        if full_url not in visited:
                            queue.append(full_url)
                except Exception:
                    continue

    except Exception as e:
        logging.error(f"Error scraping {url}: {e}")

    return domains_data

async def process_site(playwright, url):
    retries = 0
    data = []
    while retries < MAX_RETRIES:
        try:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            data = await extract_domains_from_site(page, url)
            await browser.close()
            break
        except Exception as e:
            retries += 1
            logging.warning(f"Retry {retries}/{MAX_RETRIES} for {url}: {e}")
            time.sleep(2)
    return data

async def main():
    input_file = "file.txt"  # Already uploaded
    with open(input_file, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    async with async_playwright() as p:
        for url in urls:
            logging.info(f"Processing {url}")
            site_name = sanitize_filename(get_site_name(url))
            result_file = f"{site_name}.csv"

            domains = await process_site(p, url)
            if not domains:
                print(f"⚠️ No data found for {url}")
                continue

            with open(result_file, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = list(domains[0].keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for i, row in enumerate(domains):
                    writer.writerow(row)
                    if i > 0 and i % PAUSE_EVERY == 0:
                        logging.info(f"⏳ Pausing for {PAUSE_DURATION}s after {i} domains...")
                        time.sleep(PAUSE_DURATION)

            logging.info(f"✅ Data saved to {result_file}")

if __name__ == "__main__":
    asyncio.run(main())
