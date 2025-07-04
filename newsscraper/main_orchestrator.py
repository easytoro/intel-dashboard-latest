# main_orchestrator.py

import os
import json
import asyncio
import subprocess
from urllib.parse import quote
import feedparser
import config
import url_resolver
import fallback_scraper
import uuid
import tiktoken
import time
from collections import deque

def generate_google_queries():
    """Generates a list of all Google News RSS query strings."""
    today = config.datetime.now()
    yesterday = today - config.timedelta(days=1)
    after_date = (yesterday - config.timedelta(days=1)).strftime('%Y-%m-%d')
    before_date = today.strftime('%Y-%m-%d')
    date_query = f"after:{after_date} before:{before_date}"
    all_queries = []
    for region in config.TARGET_REGIONS:
        for keywords in config.CATEGORICAL_QUERIES.values():
            keyword_str = '"' + '" OR "'.join(keywords) + '"'
            all_queries.append(f'"{region}" AND ({keyword_str}) AND {date_query}')
    for site in config.MONITORED_WEBSITES:
        all_queries.append(f'site:{site} AND {date_query}')
    return all_queries

def fetch_google_urls(queries: list[str]) -> list[str]:
    """Takes a list of queries and returns a flat list of Google News URLs."""
    google_urls = []
    print("Fetching Google News RSS feeds...")
    for query in queries:
        encoded_query = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if entry.link:
                google_urls.append(entry.link)
    print(f"-> Found {len(google_urls)} raw Google links.")
    return list(set(google_urls))

def cluster_stories(articles: list[dict], threshold: float) -> list[list[dict]]:
    """Groups articles into story clusters using a semantic sentence-transformer model."""
    if not articles or len(articles) < 2:
        return [[article] for article in articles]
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    print("  -> Loading semantic model and encoding articles...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    corpus = [f"{article.get('title', '')}. {article.get('full_text', '')[:1000]}" for article in articles]
    embeddings = model.encode(corpus, show_progress_bar=True)
    similarity_matrix = cosine_similarity(embeddings)
    print("  -> Grouping articles based on semantic similarity...")
    visited = [False] * len(articles)
    clusters = []
    for i in range(len(articles)):
        if visited[i]:
            continue
        current_cluster_indices = [i]
        visited[i] = True
        for j in range(i + 1, len(articles)):
            if not visited[j] and similarity_matrix[i][j] >= threshold:
                current_cluster_indices.append(j)
                visited[j] = True
        cluster_articles = [articles[k] for k in current_cluster_indices]
        clusters.append(cluster_articles)
    return clusters


if __name__ == "__main__":
    # --- Clean up old files ---
    output_files = ["resolved_urls.txt", "newsscraper/scraped_data.jsonl", "output_articles.jsonl", "output_stories.json"]
    for f in output_files:
        if os.path.exists(f): os.remove(f)

    # === STAGE 1: URL ACQUISITION & RESOLUTION ===
    print("\n--- STAGE 1: ACQUIRING & RESOLVING URLS ---")
    google_queries = generate_google_queries()
    raw_google_urls = fetch_google_urls(google_queries)
    clean_urls = asyncio.run(url_resolver.run_resolver(raw_google_urls))
    with open("resolved_urls.txt", "w") as f:
        for url in clean_urls: f.write(url + "\n")
    print(f"-> Resolved to {len(clean_urls)} unique article URLs.")

    # === STAGE 2: CONTENT EXTRACTION (OPTIMISTIC + FALLBACK) ===
    if clean_urls:
        print("\n--- STAGE 2: EXTRACTING CONTENT ---")
        print("-> Running initial Scrapy spider...")
        url_file_path = os.path.abspath("resolved_urls.txt")
        subprocess.run(["scrapy", "crawl", "content_spider", "-a", f"url_file={url_file_path}", "-O", "newsscraper/scraped_data.jsonl"], cwd="newsscraper", capture_output=True, text=True)
        print("-> Scrapy run complete.")
    else:
        print("No URLs to scrape. Exiting."); exit()
    fallback_data = []
    fallback_urls_path = "newsscraper/fallback_urls.txt"
    if os.path.exists(fallback_urls_path):
        with open(fallback_urls_path, "r", encoding="utf-8") as f:
            fallback_urls = [line.strip() for line in f if line.strip()]
        if fallback_urls: fallback_data = asyncio.run(fallback_scraper.run_fallback_scraper(fallback_urls))
    initial_scraped_data = []
    try:
        with open("newsscraper/scraped_data.jsonl", "r", encoding='utf-8') as f:
            for line in f: initial_scraped_data.append(json.loads(line))
    except FileNotFoundError: pass
    all_scraped_data = initial_scraped_data + fallback_data
    for article in all_scraped_data:
        article['article_id'] = str(uuid.uuid4()); article['scraped_at'] = config.datetime.now().isoformat()
    print(f"-> Total articles gathered: {len(all_scraped_data)}")

    # === STAGE 3: STORY CLUSTERING ===
    print("\n--- STAGE 3: CLUSTERING SIMILAR STORIES ---")
    if all_scraped_data:
        story_clusters = cluster_stories(all_scraped_data, config.STORY_SIMILARITY_THRESHOLD)
        print(f"-> Grouped {sum(len(c) for c in story_clusters)} articles into {len(story_clusters)} unique stories.")
    else:
        story_clusters = []
        print("-> No articles to cluster.")

    # === STAGE 4: INTELLIGENT BATCHING & RATE-LIMITED ANALYSIS ===
    print("\n--- STAGE 4: ANALYZING STORIES & CREATING RECORDS ---")
    final_articles = []
    final_stories = []
    if story_clusters:
        story_payloads = []
        for i, story_bucket in enumerate(story_clusters):
            combined_text = "\n\n---\n\n".join([f"Title: {article['title']}\n\n{article['full_text']}" for article in story_bucket])
            story_payloads.append({"story_index": i, "text_for_llm": combined_text, "original_bucket": story_bucket})
        
        print("-> Creating optimized batches based on token count...")
        encoding = tiktoken.get_encoding("cl100k_base")
        list_of_batches = []
        current_batch = []
        current_batch_tokens = 0
        for payload in story_payloads:
            num_tokens = len(encoding.encode(payload['text_for_llm']))
            if current_batch and current_batch_tokens + num_tokens > config.LLM_MAX_TOKENS_PER_CALL:
                # THIS IS THE CORRECTED LOGIC: Appending a tuple
                list_of_batches.append((current_batch, current_batch_tokens))
                current_batch = [payload]
                current_batch_tokens = num_tokens
            else:
                current_batch.append(payload)
                current_batch_tokens += num_tokens
        if current_batch:
            # THIS IS THE CORRECTED LOGIC: Appending a tuple
            list_of_batches.append((current_batch, current_batch_tokens))
        
        num_batches = len(list_of_batches)
        print(f"-> Created {num_batches} batch(es) to process {len(story_payloads)} stories.")

        all_llm_results = {}
        request_history = deque()
        tokens_in_window = 0
        for i, (batch, batch_tokens) in enumerate(list_of_batches):
            batch_num = i + 1
            now = time.time()
            while request_history and now - request_history[0][0] > 60:
                old_ts, old_tokens = request_history.popleft()
                tokens_in_window -= old_tokens
            if tokens_in_window + batch_tokens > config.LLM_TPM_LIMIT:
                time_to_wait = 60 - (now - request_history[0][0]) + 1
                print(f"  [RATE LIMIT] TPM limit would be exceeded. Waiting for {time_to_wait:.1f} seconds...")
                time.sleep(time_to_wait)
                now = time.time()
                while request_history and now - request_history[0][0] > 60:
                    old_ts, old_tokens = request_history.popleft()
                    tokens_in_window -= old_tokens
            
            print(f"  -> Processing Batch {batch_num}/{num_batches} ({batch_tokens} tokens)...")
            llm_input_data = [{"story_index": p["story_index"], "text": p["text_for_llm"]} for p in batch]
            try:
                batch_input_string = json.dumps(llm_input_data)
                analysis_results = config.analyze_article(engine_name=config.SELECTED_ENGINE, batch_input_json=batch_input_string)
                if isinstance(analysis_results, list):
                    request_history.append((time.time(), batch_tokens))
                    tokens_in_window += batch_tokens
                    for result in analysis_results: all_llm_results[result['story_index']] = result
                else:
                    print(f"  [ERROR] Analysis failed for batch {batch_num}: {analysis_results.get('error', 'Unknown Error')}")
                    continue
            except Exception as e:
                print(f"  [ERROR] Batch {batch_num} failed during processing: {e}. Skipping this batch."); continue
        
        if all_llm_results:
            print("-> Assembling final records from analysis results...")
            for payload in story_payloads:
                story_index, story_bucket = payload['story_index'], payload['original_bucket']
                final_articles.extend(story_bucket)
                if story_index in all_llm_results:
                    analysis_result = all_llm_results[story_index]
                    story_bucket.sort(key=lambda x: len(x.get('full_text', '')), reverse=True)
                    representative_article = story_bucket[0]
                    earliest_pub_date = min([a['published_at'] for a in story_bucket if a.get('published_at')], default=None)
                    story_record = {
                        "story_id": str(uuid.uuid4()),
                        "canonical_title": analysis_result.get("canonical_title", representative_article['title']),
                        "summary": analysis_result.get("summary"), "sentiment": analysis_result.get("sentiment"),
                        "key_entities": analysis_result.get("key_entities"), "suggested_category": analysis_result.get("suggested_category"),
                        "first_seen_at": earliest_pub_date, "article_ids": [a['article_id'] for a in story_bucket],
                        "source_domains": sorted(list(set(a['source_domain'] for a in story_bucket))),
                        "article_count": len(story_bucket)
                    }
                    final_stories.append(story_record)
        print(f"-> Created {len(final_stories)} story records and {len(final_articles)} article records.")

    # === STAGE 5: REPORTING ===
    print("\n--- STAGE 5: FINAL REPORT ---")
    if final_stories:
        with open("output_articles.jsonl", "w", encoding='utf-8') as f:
            for article in final_articles: f.write(json.dumps(article) + '\n')
        print(f"-> Successfully saved {len(final_articles)} articles to output_articles.jsonl")
        with open("output_stories.json", 'w', encoding='utf-8') as f:
            json.dump(final_stories, f, ensure_ascii=False, indent=2)
        print(f"-> Successfully saved {len(final_stories)} stories to output_stories.json")
    else:
        print("-> No data to save.")
    if os.path.exists(fallback_urls_path) and fallback_data:
        print(f"\n-> NOTE: {len(fallback_urls)} URLs required fallback scraping; {len(fallback_data)} were rescued.")
    else:
        print("\n-> Great! No fallbacks were necessary.")