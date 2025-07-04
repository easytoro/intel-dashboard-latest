# newsscraper/newsscraper/spiders/content_spider.py

import scrapy
from newspaper import Article, ArticleException
import os

class ContentSpider(scrapy.Spider):
    name = 'content_spider_test'
    handle_httpstatus_list = [403]

    def __init__(self, url_file=None, start_url=None, *args, **kwargs):
        """
        Initializes the spider and sets up the debug directory.
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
        Saves the raw response to a file, then attempts to parse it.
        """
        # --- THIS SAVES EVERY SINGLE RESPONSE, NO MATTER WHAT ---
        self.response_counter += 1
        # Create a unique filename for this response
        safe_filename_part = response.url.split('?')[0].split('/')[-1] or "index"
        debug_filename = os.path.join(self.debug_dir, f'{self.response_counter}_{safe_filename_part}.html')
        
        self.logger.critical(f'SAVING RAW RESPONSE for {response.url} to: {debug_filename}')
        
        with open(debug_filename, 'wb') as f:
            f.write(response.body)
        # --- END SAVE BLOCK ---

        # Your existing parsing logic continues below.
        # This code will run AFTER the file has been saved.
        if response.status == 403:
            self.logger.warning(f"Received 403 Forbidden for {response.url}. Adding to fallback list.")
            with open("fallback_urls.txt", "a") as f:
                f.write(response.url + "\n")
            return

        article_text = None
        article_title = None
        publish_date = None

        # --- STRATEGY 1: PRECISION EXTRACTION ---
        self.logger.debug(f"Attempting Strategy 1 (Precision) for {response.url}")
        try:
            article_container = response.css('article, .post, .entry-content, #main-content').get()
            if article_container:
                precision_article = Article(url=response.url)
                precision_article.download(input_html=article_container)
                precision_article.parse()
                
                if precision_article.text and len(precision_article.text) >= 150:
                    self.logger.debug("-> Strategy 1 succeeded.")
                    article_text = precision_article.text
                    article_title = precision_article.title
                    publish_date = precision_article.publish_date
            else:
                self.logger.debug("-> Strategy 1 failed: No container found.")
        except Exception as e:
            self.logger.debug(f"-> Strategy 1 failed with an exception: {e}")

        # --- STRATEGY 2: BROAD FALLBACK ---
        if not article_text:
            self.logger.debug(f"Attempting Strategy 2 (Broad) for {response.url}")
            try:
                broad_article = Article(url=response.url)
                broad_article.download(input_html=response.text)
                broad_article.parse()
                
                if broad_article.text and len(broad_article.text) >= 150:
                    self.logger.debug("-> Strategy 2 succeeded.")
                    article_text = broad_article.text
                    article_title = broad_article.title
                    publish_date = broad_article.publish_date
                else:
                    self.logger.debug("-> Strategy 2 failed: Content too short.")
            except Exception as e:
                self.logger.debug(f"-> Strategy 2 failed with an exception: {e}")
        
        # --- FINAL CHECK AND YIELD ---
        if article_text:
            yield {
                'url': response.url,
                'title': article_title,
                'published_at': publish_date.isoformat() if publish_date else None,
                'full_text': article_text,
                'source_domain': response.url.split('/')[2]
            }
        else:
            self.logger.warning(f"All parsing strategies failed for {response.url}. Adding to main fallback list.")
            with open("fallback_urls.txt", "a") as f:
                f.write(response.url + "\n")