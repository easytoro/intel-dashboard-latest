# dashboard.py

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timezone
from st_keyup import st_keyup

# --- Page Configuration ---
st.set_page_config(
    layout="wide",
    page_title="Intelligence Briefing",
    page_icon="📰"
)

# --- Data Loading Function (FINAL, ROBUST VERSION) ---
@st.cache_data
def load_data() -> tuple[list[dict], dict[str, dict], str | None]:
    """
    Loads the latest stories and articles, safely handling missing dates.
    Returns:
        - A list of story dictionaries.
        - A dictionary mapping article_id to article data.
        - The name of the stories file loaded.
    """
    stories_file = Path("output_stories.json")
    articles_file = Path("output_articles.jsonl")

    if not stories_file.exists() or not articles_file.exists():
        return [], {}, None

    # Load the stories
    with open(stories_file, 'r', encoding='utf-8') as f:
        stories_data = json.load(f)
    
    # Load the articles and create a lookup map
    articles_map = {}
    with open(articles_file, 'r', encoding='utf-8') as f:
        for line in f:
            article = json.loads(line)
            articles_map[article['article_id']] = article

    # This is our universal, timezone-aware default for any story with a missing/bad date.
    AWARE_MIN_DATE = datetime.min.replace(tzinfo=timezone.utc)

    for story in stories_data:
        pub_date_str = story.get('first_seen_at')
        
        # This logic robustly handles all date cases.
        if pub_date_str:
            try:
                # If the date string exists, try to parse it.
                dt = pd.to_datetime(pub_date_str)
                # Now that we know dt is a real datetime, we can safely check tzinfo.
                story['first_seen_at_dt'] = dt.tz_convert('UTC') if dt.tzinfo else dt.tz_localize('UTC')
            except (ValueError, TypeError):
                # If parsing fails on a non-empty string, use the default.
                story['first_seen_at_dt'] = AWARE_MIN_DATE
        else:
            # If the date string was None or empty from the start, use the default.
            story['first_seen_at_dt'] = AWARE_MIN_DATE
    
    return stories_data, articles_map, stories_file.name

# --- Reusable UI Function for Story Display ---
def display_story_expander(story_dict, articles_map):
    """Takes a story dictionary and displays it as a Streamlit expander."""
    category_icons = {
        "Technology": "💻",
        "Corporate Finance": "💼",
        "Healthcare Services": "🏥",
        "Government & Policy": "⚖️",
        "Science & Research": "🔬",
        "Social Media": "📱"
    }
    category = story_dict.get('suggested_category')
    icon = category_icons.get(category, "📄")
    
    with st.expander(f"{icon} **{story_dict.get('canonical_title', 'No Title')}**"):
        st.markdown(f"**AI Summary:** *{story_dict.get('summary', 'N/A')}*")
        
        meta_col1, meta_col2 = st.columns([2,1])
        with meta_col1:
            st.write(f"**Key Entities:** " + " ".join([f"`{entity}`" for entity in story_dict.get('key_entities', [])]))
            st.write(f"**AI Sentiment:** {story_dict.get('sentiment', 'N/A')}")
        with meta_col2:
            st.write(f"**Category:** `{story_dict.get('suggested_category', 'N/A')}`")
            st.write(f"**Source Articles:** `{story_dict.get('article_count', 0)}`")

        st.markdown("---")
        st.subheader("Source Articles")
        
        # Display each source article as a link
        for article_id in story_dict.get('article_ids', []):
            article = articles_map.get(article_id)
            if article:
                st.markdown(f"- [{article.get('title')}]({article.get('url')}) - *{article.get('source_domain')}*")


# --- Main Application ---
stories_data, articles_map, filename = load_data()

if not stories_data:
    st.title("Intelligence Briefing")
    st.warning("No data files found (`output_stories.json`, `output_articles.jsonl`). Please run the main scraper first.")
    st.stop()

# --- Sidebar Navigation ---
# This is now dynamically generated from the stories data.
all_categories = sorted(list(set(story.get('suggested_category') for story in stories_data if story.get('suggested_category'))))
page_options = ["Dashboard Overview", "All Stories"] + all_categories

st.sidebar.title("Navigation")
st.sidebar.info(f"Briefing loaded: **{filename}**")
selected_page = st.sidebar.radio("Menu", page_options, key="page_selector", label_visibility="collapsed")

# ==============================================================================
# VIEW 1: DASHBOARD OVERVIEW
# ==============================================================================
if selected_page == "Dashboard Overview":
    st.title("Dashboard Overview")
    st.write("A high-level view of the stories in this briefing.")
    
    selected_overview_categories = st.multiselect("Filter by Category", all_categories, key="overview_cat_filter")

    # Filtering logic for stories
    overview_data = stories_data
    if selected_overview_categories:
        overview_data = [
            story for story in overview_data 
            if story.get('suggested_category') in selected_overview_categories
        ]
    
    st.markdown("---")
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Stories in View", len(overview_data))
    m_col2.metric("Total Unique Categories", len(all_categories))
    
    st.subheader("Story Count by Category")
    if overview_data:
        # Create a pandas Series directly for efficient counting
        category_counts = pd.Series([story['suggested_category'] for story in overview_data]).value_counts()
        st.bar_chart(category_counts)
    else:
        st.write("No stories to display based on filters.")

# ==============================================================================
# VIEW 2: STORY FEEDS
# ==============================================================================
else:
    if selected_page == "All Stories":
        st.title(f"All Stories")
        page_category_filter = None
    else:
        st.title(f"Feed: {selected_page}")
        page_category_filter = selected_page

    search_key = f"search_{selected_page}"
    search_query = st_keyup("Search titles & summaries (live)", debounce=300, key=search_key)
    st.markdown("---")

    # High-performance filtering for the feed
    feed_data = stories_data
    
    if page_category_filter:
        feed_data = [story for story in feed_data if story.get('suggested_category') == page_category_filter]

    if search_query:
        query = search_query.lower()
        feed_data = [
            story for story in feed_data 
            if query in story.get('canonical_title', '').lower() or query in story.get('summary', '').lower()
        ]
        
    st.write(f"Displaying **{len(feed_data)}** stories.")
    if not feed_data:
        st.info("No stories match the current filters.")
    else:
        # The sort key is now completely safe because we guarantee `first_seen_at_dt`
        # is always a valid, timezone-aware datetime object.
        feed_data.sort(key=lambda x: x['first_seen_at_dt'], reverse=True)
        
        for story_dict in feed_data:
            display_story_expander(story_dict, articles_map)