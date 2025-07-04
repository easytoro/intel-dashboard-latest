# newsscraper/newsscraper/spiders/content_spider.py

import scrapy
from newspaper import Article, ArticleException
import os

class ContentSpider(scrapy.Spider):
    name = 'content_spider'
    handle_httpstatus_list = [403]
    
    # --- Configuration ---
    PRECISION_SELECTORS = '.entry-content, .sponsored-article-content'
    MIN_TEXT_LENGTH = 150
    # The pipeline will look for this filename
    FALLBACK_FILENAME = "fallback_urls.txt" 

    def __init__(self, url_file=None, start_url=None, *args, **kwargs):
        """Initializes the spider."""
        super(ContentSpider, self).__init__(*args, **kwargs)
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

    def _extract_with_newspaper(self, html, url):
        """Helper function to encapsulate newspaper3k extraction logic."""
        try:
            article = Article(url=url)
            article.download(input_html=html)
            article.parse()
            if not article.text or len(article.text) < self.MIN_TEXT_LENGTH:
                raise ArticleException(f"Extracted text is too short ({len(article.text)} chars).")
            return article
        except Exception as e:
            self.logger.debug(f"Newspaper extraction failed for {url}: {e}")
            return None

    def parse(self, response):
        """Cascading fallback: Precision -> General -> Fail."""
        if response.status == 403:
            self.logger.warning(f"403 Forbidden for {response.url}. Yielding as failure.")
            yield {'failed_url': response.url, 'reason': '403 Forbidden'}
            return

        # --- Try Precision Strategy ---
        article_html_container = response.css(self.PRECISION_SELECTORS).get()
        article = None
        if article_html_container:
            self.logger.info(f"Trying PRECISION strategy for {response.url}.")
            article = self._extract_with_newspaper(html=article_html_container, url=response.url)

        # --- Fallback to General Strategy ---
        if not article:
            self.logger.info(f"Trying GENERAL strategy for {response.url}.")
            article = self._extract_with_newspaper(html=response.text, url=response.url)
        
        # --- Yield Success or Failure ---
        if article:
            pub_date = article.publish_date
            yield {
                'url': response.url,
                'title': article.title,
                'published_at': pub_date.isoformat() if pub_date else None,
                'full_text': article.text,
                'source_domain': response.url.split('/')[2],
            }
        else:
            self.logger.warning(f"All extraction strategies FAILED for {response.url}.")
            yield {'failed_url': response.url, 'reason': 'Extraction Failed'}