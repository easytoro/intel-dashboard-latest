# fallback_scraper.py

import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlparse
import config

async def scrape_single_page(page, url: str) -> dict | None:
    """
    Uses a single Playwright page to scrape the content from a URL that
    likely requires JavaScript rendering.
    """
    try:
        # Go to the URL, wait for the page to be mostly loaded.
        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
        
        # A simple but effective heuristic: look for the <main> element
        # which semantically should contain the primary content.
        # This can be made more robust with more selectors.
        main_content = page.locator('main, article, [role=main]')
        
        # Wait for the element to be visible
        await main_content.first.wait_for(timeout=10000)
        
        # Extract the text and title
        full_text = await main_content.first.inner_text()
        title = await page.title()

        if not full_text or len(full_text) < 150:
            print(f"  [FALLBACK-FAIL] Content too short for: {url}")
            return None

        print(f"  [FALLBACK-SUCCESS] Scraped: {url}")
        
        # Return data in the same format as the Scrapy spider for consistency
        return {
            'url': url,
            'title': title,
            'published_at': None, # We don't have a reliable way to get this here
            'full_text': full_text,
            'source_domain': urlparse(url).netloc
        }
        
    except PlaywrightTimeoutError:
        print(f"  [FALLBACK-FAIL] Timeout scraping: {url}")
        return None
    except Exception as e:
        print(f"  [FALLBACK-FAIL] Error scraping {url}: {type(e).__name__}")
        return None

async def run_fallback_scraper(fallback_urls: list[str]) -> list[dict]:
    """
    Scrapes a list of fallback URLs in parallel using Playwright.
    """
    scraped_data = []
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_BROWSERS) # Reuse config

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        async def scrape_with_semaphore(url):
            async with semaphore:
                page = await browser.new_page(user_agent=config.USER_AGENT)
                # We DON'T block resources here because we need CSS/JS to render the page
                data = await scrape_single_page(page, url)
                if data:
                    scraped_data.append(data)
                await page.close()

        print(f"\n--- STAGE 2.5: RUNNING FALLBACK SCRAPER ---")
        print(f"Attempting to scrape {len(fallback_urls)} URLs with Playwright...")
        tasks = [scrape_with_semaphore(url) for url in fallback_urls]
        await asyncio.gather(*tasks)
        await browser.close()
    
    print(f"-> Successfully scraped {len(scraped_data)} articles via fallback.")
    return scraped_data