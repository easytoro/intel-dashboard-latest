# newsscraper/newsscraper/spiders/content_spider.py

import scrapy
from newspaper import Article, ArticleException
import os

class ContentSpider(scrapy.Spider):
    name = 'content_spider_WORKS'
    handle_httpstatus_list = [403]

    def __init__(self, url_file=None, start_url=None, *args, **kwargs):
        """
        Initializes the spider, sets up URL sources, and prepares a
        debug directory for saving raw server responses.
        """
        super(ContentSpider, self).__init__(*args, **kwargs)

        # --- THIS IS THE SETUP FOR SAVING EVERY RESPONSE ---
        self.debug_dir = 'DEBUG_RAW_RESPONSES'
        os.makedirs(self.debug_dir, exist_ok=True)
        self.response_counter = 0
        # --- END SETUP ---

        # Your existing __init__ logic
        self.start_urls = []
        if url_file:
            if not os.path.exists(url_file):
                raise FileNotFoundError(f"The URL file was not found at: {url_file}")
            with open(url_file, 'r') as f:
                self.start_urls = [line.strip() for line in f if line.strip()]
        elif start_url:
            self.start_urls = [start_url]
        else:
             raise ValueError("Spider must be initialized with 'url_file' or 'start_url'")
        
        self.logger.info(f"Initialized spider for {len(self.start_urls)} URL(s).")
        
        fallback_path = "fallback_urls.txt"
        if os.path.exists(fallback_path):
            os.remove(fallback_path)

    def parse(self, response):
        """
        First, saves the raw HTML response for debugging.
        Then, uses a hyper-specific selector to find the content container
        and feeds that clean HTML to Newspaper3k for parsing.
        """
        # --- THIS SAVES EVERY SINGLE RESPONSE, NO MATTER WHAT ---
        self.response_counter += 1
        safe_filename_part = response.url.split('?')[0].split('/')[-1] or "index"
        debug_filename = os.path.join(self.debug_dir, f'{self.response_counter}_{safe_filename_part}.html')
        
        self.logger.critical(f'SAVING RAW RESPONSE for {response.url} to: {debug_filename}')
        
        with open(debug_filename, 'wb') as f:
            f.write(response.body)
        # --- END SAVE BLOCK ---

        # Handle 403 errors by adding to fallback and stopping
        if response.status == 403:
            self.logger.warning(f"Received 403 Forbidden for {response.url}. Adding to fallback list.")
            with open("fallback_urls.txt", "a") as f:
                f.write(response.url + "\n")
            return

        try:
            # --- THE DEFINITIVE FIX ---
            # Create a selector that looks for EITHER of the two content containers we've identified.
            content_selector = '.entry-content, .sponsored-article-content'
            
            # Extract the HTML from the container we found.
            article_html_container = response.css(content_selector).get()

            if not article_html_container:
                # If neither of our specific containers are found, this page is truly different.
                # It will fail and go to the Playwright fallback.
                raise ArticleException(f"Could not find a known content container with selector: '{content_selector}'")

            # Feed only this clean, targeted HTML snippet to newspaper3k.
            article = Article(url=response.url)
            article.download(input_html=article_html_container)
            article.parse()

            # Your quality check is still vital.
            if not article.text or len(article.text) < 150:
                raise ArticleException(f"Content extracted from container was too short (len: {len(article.text)}).")

            # If we get here, parsing was a success.
            self.logger.info(f"Successfully parsed content for {response.url} using precise container.")
            
            pub_date = article.publish_date
            yield {
                'url': response.url,
                'title': article.title,
                'published_at': pub_date.isoformat() if pub_date else None,
                'full_text': article.text,
                'source_domain': response.url.split('/')[2]
            }

        except Exception as e:
            # If our precise strategy fails for any reason, the URL is sent to Playwright.
            self.logger.warning(f"Precise parsing strategy failed for {response.url}: {e}. Adding to main fallback list.")
            with open("fallback_urls.txt", "a") as f:
                f.write(response.url + "\n")