import os
import asyncio
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from langchain_core.tools import tool
try:
    from langchain_community.utilities import SearxSearchWrapper
    from langchain_tavily import TavilySearch
    from langchain_community.document_loaders import AsyncHtmlLoader
    from langchain_community.document_transformers import Html2TextTransformer
    from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
    from langchain_community.tools.playwright.utils import create_async_playwright_browser
    HAS_WEB_DEPS = True
except ImportError:
    HAS_WEB_DEPS = False

@tool
async def search_web(query: str, search_depth: str = "basic") -> str:
    """
    Search the web for information using Tavily or SearXNG.
    Use this for finding general information, documentation, or news.
    """
    if not HAS_WEB_DEPS:
        return "Error: Web research dependencies not installed."
        
    tavily_key = os.environ.get("TAVILY_API_KEY")
    if tavily_key:
        try:
            search = TavilySearch(max_results=5, search_depth=search_depth)
            results = await search.ainvoke({"query": query})
            print(results)
            return str(results)
        except Exception as e:
            return f"Tavily search failed: {str(e)}"
    
    searx_host = os.environ.get("SEARX_HOST", "http://localhost:8080")
    try:
        search = SearxSearchWrapper(searx_host=searx_host)
        return search.run(query)
    except Exception as e:
        return f"SearXNG search failed: {str(e)}. Please set TAVILY_API_KEY or ensure SearXNG is running."

@tool
async def read_url(url: str, start_char: int = 0) -> str:
    """
    Read the content of a specific URL and convert it to clean text (Markdown).
    Supports pagination to read large content in chunks.
    Args:
        url: The URL to read
        start_char: Starting character index for pagination (default: 0)
    """
    if not HAS_WEB_DEPS:
        return "Error: Web research dependencies not installed."
        
    try:
        loader = AsyncHtmlLoader([url])
        docs = loader.load()
        html2text = Html2TextTransformer()
        docs_transformed = html2text.transform_documents(docs)
        if docs_transformed:
            # Get full content
            full_content = docs_transformed[0].page_content
            total_chars = len(full_content)
            
            # Slice content (4000 char window)
            window_size = 4000
            end_char = min(start_char + window_size, total_chars)
            content_slice = full_content[start_char:end_char]
            
            # Add pagination info
            if total_chars > end_char:
                return (
                    f"{content_slice}\n\n"
                    f"--- PAGINATION INFO ---\n"
                    f"Showing characters {start_char}-{end_char} of {total_chars}.\n"
                    f"To read the next chunk, use: read_url('{url}', start_char={end_char})"
                )
            
            return content_slice
        return "No content could be extracted from the URL."
    except Exception as e:
        return f"Failed to read URL: {str(e)}"

# Global browser instance for stateful interaction
_BROWSER = None

async def get_browser():
    global _BROWSER
    if _BROWSER is None:
        _BROWSER = create_async_playwright_browser()
    return _BROWSER

@tool
async def browse_interactive(action: str, url: Optional[str] = None, selector: Optional[str] = None, text: Optional[str] = None) -> str:
    """
    Stateful interactive browser tool. 
    Actions: 'navigate', 'click', 'type', 'capture', 'get_elements'.
    """
    if not HAS_WEB_DEPS:
        return "Error: Web research dependencies not installed."
        
    browser = await get_browser()
    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=browser)
    tools = toolkit.get_tools()
    tools_by_name = {t.name: t for t in tools}
    
    try:
        if action == "navigate" and url:
            return await tools_by_name["navigate_browser"].arun({"url": url})
        elif action == "click" and selector:
            return await tools_by_name["click_element"].arun({"selector": selector})
        elif action == "capture":
            # Taking a screenshot for vision analysis (concept)
            page = await browser.new_page() # Simplified for now
            if url: await page.goto(url)
            # In a real implementation, we'd capture and return the image path/base64
            # For now, return text extract as fallback
            return await tools_by_name["extract_text"].arun({})
        elif action == "get_elements" and selector:
            return await tools_by_name["get_elements"].arun({"selector": selector})
        
        return f"Unsupported action: {action}"
    except Exception as e:
        return f"Browser action '{action}' failed: {str(e)}"

WEB_TOOLS = [search_web, read_url, browse_interactive]
