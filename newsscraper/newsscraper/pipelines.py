# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem
import os


class NewsscraperPipeline:
    def process_item(self, item, spider):
        return item

class FallbackUrlPipeline:
    def open_spider(self, spider):
        """
        Called when the spider is opened.
        It finds the fallback filename from the spider's attributes.
        It clears the old fallback file, which your orchestrator was doing before.
        """
        self.fallback_filepath = os.path.join(
            os.path.dirname(__file__), '..', # This ensures the file is in the project root (newsscraper/)
            getattr(spider, 'FALLBACK_FILENAME', 'fallback_urls.txt')
        )
        
        # This pipeline now handles cleaning up the old file.
        if os.path.exists(self.fallback_filepath):
            os.remove(self.fallback_filepath)
        
        self.file = open(self.fallback_filepath, 'a')
        spider.logger.info(f"Opened fallback file for writing: {self.fallback_filepath}")

    def close_spider(self, spider):
        """Called when the spider is closed."""
        self.file.close()

    def process_item(self, item, spider):
        """
        This method is called for every item yielded by the spider.
        """
        # We check if the item is a "failure" item by looking for the 'failed_url' key.
        if 'failed_url' in item:
            self.file.write(item['failed_url'] + '\n')
            # We "drop" the item so it doesn't get written to scraped_data.jsonl
            raise DropItem(f"URL failed and was written to fallback file: {item['failed_url']}")
        else:
            # This is a successful item. Let it pass on to the next pipeline 
            # or (in your case) the JSONL feed exporter.
            return item