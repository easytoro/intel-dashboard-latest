# config.py

# --- Core Libraries ---
import random
from datetime import datetime, timedelta
import os
import json
from google import genai
from pydantic import BaseModel

# ==============================================================================
#  CONFIGURATION
# ==============================================================================
# Define target regions and categorical queries in a structured way.
TARGET_REGIONS = [
    "Texas", "Colorado"
] 

CATEGORICAL_QUERIES = {
    "Mental Health Services": [
        "mental health", "behavioral health", "telehealth therapy", "psychiatric care"
    ],
    "Regulatory & Policy": [
        "healthcare policy", "addiction legislation", "substance use legislation", "SAMHSA", "substance use policy", "mental health policy", "opioid policy", "mental health legislation"
    ],
    "Business & M&A": [
        "clinic expansion", "healthcare acquisition", "telehealth investment", "HCA Healthcare", "substance use acquisition", "addiction treatment acquisition", "addiction treatment business",
    ],
    "Substance Use & Opioids": [
        "opioid crisis", "addiction treatment", "substance abuse", "fentanyl", "overdose", "substance use disorder", "opioid epidemic",
        "opioid addiction", "opioid treatment", "opioid overdose", "opioid use", "opioid recovery", "opioid prevention", "opioid policy",
    ],
    "Behavioral Health:": [
        "SUD", "substance use disorder", "OBOT", "RCT", "MAT", "medication-assisted treatment", "opioid use disorder",
        "opioid treatment program", "opioid recovery", "opioid prevention"
    ],
    "Clinic Based": [
        "inpatient care addiction", "outpatient services addiction", "mental health clinic", "substance use clinic", 
        "addiction rehabilitation center", "addiction treatment center", 
    ],
    "Behavioral Health Companies": [
        "Universal Health Services", "Talkiatry", "Mindpath Health", "BHB", "Acadia Healthcare Company", 
        "BayMark Health", "Banyan Treatment Centers", "Brightline", "Cerebral", "All Points North",
        "Cenikor Foundation", "Clearview Treatment Programs", "Compass Health Network",
    ]
}

MONITORED_WEBSITES = [
    "bhbusiness.com",
    "beckersbehavioralhealth.com"
]

OUTPUT_CATEGORIES = [
    "Behavioral Health",
    "Regulatory & Policy",
    "Business & M&A",
    "Substance Use & Opioids",
    "Technology & Innovation",
    "Healthcare Services",
    "Public Health",
    "Insurance & Coverage",
    "Research & Studies",
    "Social Media",
    "Community Impact", 
]

# --- Scraping Configuration ---
MAX_CONCURRENT_BROWSERS = 20
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'

STORY_SIMILARITY_THRESHOLD = 0.6

# --- Analysis Engine Configuration ---
SELECTED_ENGINE = 'gemini'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
LLM_MAX_TOKENS_PER_CALL = 50000
LLM_TPM_LIMIT = 250000

# ==============================================================================
#  ANALYSIS ENGINES
# ==============================================================================

class StoryAnalysis(BaseModel):
    story_index: int
    canonical_title: str
    summary: str
    sentiment: str
    key_entities: list[str]
    locations: list[str]
    suggested_category: str

def mock_analysis_engine(article_text: str) -> dict:
    """A fake analysis engine for fast, free, and predictable testing."""
    return {
        "llm_canonical_title": "This is a Mock Canonical Title for the Story",
        "llm_summary": "This is a mock summary of the article.",
        "llm_sentiment": random.choice(["Positive", "Neutral", "Negative"]),
        "llm_key_entities": ["Mock Company A", "Mock Person B"],
        "llm_suggested_category": random.choice(list(CATEGORICAL_QUERIES.keys()))
    }
    
def gemini_analysis_engine(batch_input_json: str) -> dict | list:
    """
    Analyzes a batch of stories using Gemini's native JSON mode for reliable structured output.
    """
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY environment variable not set."}

    try:
        client = genai.Client()
        model_name = "gemini-2.5-flash" 
    
        prompt = f"""
            You are an expert news analysis engine. Your task is to process a batch of news stories.
            For each story provided, you must perform the following analysis independently. Do not let information from one story influence another. Provide
            a one sentence summary for each story.

            The input is a JSON array of stories, where each object has a 'story_index' and a 'text'.
            Your output will be constrained to a JSON schema.

            Base your `suggested_category` on this list of allowed categories: {OUTPUT_CATEGORIES}

            Here is the batch of stories to analyze:
            {batch_input_json}
            """
            
        print(f"    -> Sending request to Gemini API model: '{model_name}'...")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": list[StoryAnalysis],
            }
        )
        
        # CORRECTED: The .parsed attribute already returns a list of dictionaries.
        # No need to call .model_dump().
        if isinstance(response.parsed, list):
            return [item.model_dump() for item in response.parsed]
        else:
            # Handle cases where the model might return an empty or non-list response (e.g., safety block)
            print(f"  [WARNING] Gemini API did not return a list of results. Response was: {response.text}")
            return []
        
    except Exception as e:
        error_msg = f"An unexpected error occurred with the Gemini API call: {e}"
        print(f"  [FATAL ERROR] {error_msg}")
        return {"error": str(e)}
    
ANALYSIS_ENGINES = {
    'mock': mock_analysis_engine,
    'gemini':  gemini_analysis_engine,
}

def analyze_article(engine_name: str, **kwargs) -> dict:
    """Generic analysis orchestrator."""
    try:
        engine_function = ANALYSIS_ENGINES[engine_name]
        return engine_function(**kwargs)
    except Exception as e:
        print(f"ERROR: Analysis engine '{engine_name}' failed: {e}")
        return {"error": str(e)}