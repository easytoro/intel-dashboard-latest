# newsscraper/newsscraper/spiders/content_spider.py

import scrapy
from newspaper import Article, ArticleException
import os

class ContentSpider(scrapy.Spider):
    name = 'content_spider'
    handle_httpstatus_list = [403]

    def __init__(self, url_file=None, start_url=None, *args, **kwargs):
        """
        Initializes the spider.
        """
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
        
        fallback_path = "fallback_urls.txt"
        if os.path.exists(fallback_path):
            os.remove(fallback_path)

    def parse(self, response):
        """
        A robust parsing method that uses a simple, clear fork.
        - If it detects a known "problem site" layout, it uses a precision strategy.
        - Otherwise, it uses the general "whole page" strategy that works for most other sites.
        """
        if response.status == 403:
            self.logger.warning(f"Received 403 Forbidden for {response.url}. Adding to fallback list.")
            with open("fallback_urls.txt", "a") as f:
                f.write(response.url + "\n")
            return

        # --- THE FORK: Check if this is the problem site's layout ---
        content_selector = '.entry-content, .sponsored-article-content'
        article_html_container = response.css(content_selector).get()

        if article_html_container:
            # --- PATH A: PRECISION STRATEGY (For the problem site) ---
            self.logger.info(f"Detected specific container for {response.url}. Using PRECISION strategy.")
            try:
                article = Article(url=response.url)
                article.download(input_html=article_html_container)
                article.parse()

                if not article.text or len(article.text) < 150:
                    raise ArticleException("Content extracted from container was too short.")
                
                # If we get here, it worked. Yield the data.
                pub_date = article.publish_date
                yield {
                    'url': response.url,
                    'title': article.title,
                    'published_at': pub_date.isoformat() if pub_date else None,
                    'full_text': article.text,
                    'source_domain': response.url.split('/')[2]
                }
                return # IMPORTANT: Exit after success.

            except Exception as e:
                # If ANY part of the precision strategy failed, send to fallback.
                self.logger.warning(f"Precision strategy FAILED for {response.url}: {e}. Adding to fallback.")
                with open("fallback_urls.txt", "a") as f:
                    f.write(response.url + "\n")
                return
        
        else:
            # --- PATH B: GENERAL STRATEGY (For the 99% of other sites) ---
            self.logger.info(f"No specific container found for {response.url}. Using GENERAL strategy.")
            try:
                article = Article(url=response.url)
                article.download(input_html=response.text) # Use the whole page
                article.parse()

                if not article.text or len(article.text) < 150:
                    raise ArticleException("Content extracted from whole page was too short.")
                
                # If we get here, it worked. Yield the data.
                pub_date = article.publish_date
                yield {
                    'url': response.url,
                    'title': article.title,
                    'published_at': pub_date.isoformat() if pub_date else None,
                    'full_text': article.text,
                    'source_domain': response.url.split('/')[2]
                }
                return # IMPORTANT: Exit after success.
            
            except Exception as e:
                # If ANY part of the general strategy failed, send to fallback.
                self.logger.warning(f"General strategy FAILED for {response.url}: {e}. Adding to fallback.")
                with open("fallback_urls.txt", "a") as f:
                    f.write(response.url + "\n")
                return