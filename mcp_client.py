import os
import sys
import asyncio
import certifi

from pathlib import Path
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")

llm = ChatGroq(
   model = "openai/gpt-oss-120b",
   api_key = GROQ_API_KEY
)

client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
        },
        "Aviationstack MCP": {
            "transport": "stdio",
            "command": "uvx",
            "args": ["aviationstack-mcp"],
            "env": {
                "AVIATION_STACK_API_KEY": f"{AVIATION_STACK_API_KEY}"
            },
        },


       "weather": {
          "transport": "stdio",
          "command": sys.executable,
          "args": [
             str(Path(__file__).resolve().parent / "custom_weather_mcp_server.py")
             ],
          "env": { **os.environ, "OPENWEATHER_API_KEY": str(OPENWEATHER_API_KEY), },
         },
     }
)




_tools_cache = {}


async def get_server_tools(server_name: str):
    if server_name not in _tools_cache:
        _tools_cache[server_name] = await client.get_tools(server_name=server_name)
    return _tools_cache[server_name]


def pick_tool(tools, tool_name: str):
    for t in tools:
        if t.name == tool_name:
            return t
    raise ValueError(f"Tool '{tool_name}' not found. Available: {[t.name for t in tools]}")




async def tavily_mcp_search(query: str):
    tools = await get_server_tools("tavily")
    tool = pick_tool(tools, "tavily_search")
    return await asyncio.wait_for(tool.ainvoke({"query": query}), timeout=25)




async def aviation_mcp_call(tool_name: str, tool_args: dict = None):
    tools = await get_server_tools("Aviationstack MCP")
    tool = pick_tool(tools, tool_name)
    return await asyncio.wait_for(tool.ainvoke(tool_args or {}), timeout=30)


async def aviation_airports_and_airlines():
    airports, airlines = await asyncio.gather(
        aviation_mcp_call("list_airports"),
        aviation_mcp_call("list_airlines"),
    )
    return airports, airlines



async def weather_and_forecast(city: str):
    tools = await get_server_tools("weather")
    weather_tool = pick_tool(tools, "get_curr_weather")
    forecast_tool = pick_tool(tools, "get_forecast")
    weather, forecast = await asyncio.wait_for(
        asyncio.gather(
            weather_tool.ainvoke({"city": city}),
            forecast_tool.ainvoke({"city": city}),
        ),
        timeout=30,
    )
    return weather, forecast



def extract_destination(query: str) -> str:
    prompt = f"Extract the destination city or country. Return only its name.\nRequest: {query}"

    response = llm.invoke(prompt)
    destination = str(response.content).strip()

    if not destination:
        raise ValueError(
            "The destination could not be extracted."
        )

    return destination