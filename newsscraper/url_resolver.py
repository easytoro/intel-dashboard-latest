import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urlparse
import config

async def resolve_url(page, google_url: str) -> str | None:
    """
    Uses a single Playwright page to resolve one Google redirect URL.
    This version uses the correct `page.wait_for_url` method.
    """
    try:
        # Go to the URL. 'commit' is often enough and faster for redirects.
        # 'load' or 'domcontentloaded' are also fine.
        await page.goto(google_url, wait_until='commit', timeout=15000)

        # The key change: Wait for the URL to no longer be a google.com domain.
        # This correctly handles the HTTP redirect.
        await page.wait_for_url(
            lambda url: "google.com" not in urlparse(url).netloc,
            timeout=15000
        )
        
        final_url = page.url
        print(f"  [SUCCESS] Resolved to: {final_url}")
        return final_url
        
    except PlaywrightTimeoutError:
        print(f"  [FAILURE] Timeout resolving: {google_url}")
        return None
    except Exception as e:
        # This will catch other potential errors (e.g., net::ERR_CONNECTION_REFUSED)
        print(f"  [FAILURE] Error resolving {google_url}: {type(e).__name__}")
        return None

async def run_resolver(google_urls: list[str]) -> list[str]:
    """
    Resolves a list of Google URLs in parallel using a pool of Playwright pages.
    """
    final_urls = set() # Use a set from the start to handle duplicates automatically
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_BROWSERS)

    async with async_playwright() as p:
        # Use a more robust user-agent if you have one
        browser = await p.chromium.launch(headless=True)
        
        async def resolve_with_semaphore(url):
            async with semaphore:
                # Using a shared browser context can be more efficient
                page = await browser.new_page(user_agent=config.USER_AGENT)
                
                # Block common resource types we don't need for resolving a URL
                await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())

                resolved = await resolve_url(page, url)
                if resolved:
                    final_urls.add(resolved)
                await page.close()

        print(f"Resolving {len(google_urls)} URLs with up to {config.MAX_CONCURRENT_BROWSERS} concurrent browsers...")
        tasks = [resolve_with_semaphore(url) for url in google_urls]
        await asyncio.gather(*tasks)
        await browser.close()

    return list(final_urls) # Return unique URLs