from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()
client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def tavily_search(query: str):
    """
    Search for travel information using the Tavily API.
    """
    response = client.search(query=query,
                             max_results=5
                             )
    results = []

    for i, r in enumerate(response['results']):
        title = r.get('title', 'unknown')
        url = r.get('url', '')
        snippet = r.get('content', '').strip()
        #keep only the first 300 characters to avoid wall-of-text
        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(' ', 1)[0] + '...'

        results.append(f"{i+1}. {title}\n{url}\n{snippet}\n")

        
    return "\n".join(results)    