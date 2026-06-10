#!/usr/bin/env python3
"""
Sophia Web Search Module
Provides internet search capability for Sophia Elya
"""
import requests
import json
import re
from typing import Optional, List, Dict

# DuckDuckGo instant answers (no API key needed)
DDG_API = "https://api.duckduckgo.com/"

def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo"""
    try:
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1
        }
        resp = requests.get(DDG_API, params=params, timeout=10)
        data = resp.json()

        results = []

        # Abstract (main answer)
        if data.get("Abstract"):
            results.append(f"**Summary**: {data['Abstract']}")
            if data.get("AbstractSource"):
                results.append(f"Source: {data['AbstractSource']}")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text'][:200]}")

        # Infobox
        if data.get("Infobox"):
            for item in data["Infobox"].get("content", [])[:3]:
                if item.get("label") and item.get("value"):
                    results.append(f"{item['label']}: {item['value']}")

        if results:
            return "\n".join(results)
        else:
            return f"No direct results for '{query}'. Try a more specific search."

    except Exception as e:
        return f"Search error: {str(e)}"

def fetch_url(url: str, max_chars: int = 2000) -> str:
    """Fetch and extract text from a URL"""
    try:
        headers = {"User-Agent": "Sophia-Elya/1.0 (ElyanLabs AI Research)"}
        resp = requests.get(url, headers=headers, timeout=15)
        # Simple text extraction (remove HTML tags)
        text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"Fetch error: {str(e)}"

def search_and_summarize(query: str) -> Dict:
    """Search and return structured results"""
    return {
        "query": query,
        "results": web_search(query),
        "source": "DuckDuckGo Instant Answers"
    }

if __name__ == "__main__":
    # Test
    print("Testing Sophia Web Search...")
    print("-" * 50)
    result = web_search("IBM POWER8 processor specifications")
    print(result)
