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

async def get_all_tools():
    for name in client.connections:
        try:
            tools = await client.get_tools(server_name=name)
            print(name, "OK ->", [t.name for t in tools])
        except BaseException as e:
            print(name, "FAILED ->", repr(e))

search_tool = None
aviation_tools = None            

async def initialize_mcp():

  global search_tool
  global aviation_tools

  if search_tool is not None and aviation_tools:
    return

  tools = await client.get_tools()
  print("\nAvailable MCP Tools:\n")

  for tool in tools:
    print(tool.name)

  search_tool = next(
    tool for tool in tools if tool.name =="tavily_search"
  )  

  aviation_tools = {
    tool.name:tool
    for tool in tools
    if tool.name != "tavily_search"
  }

async def tavily_mcp_search(query:str):
  await initialize_mcp()
  result = await search_tool.ainvoke(
    {
      "query":query
    }
  )
  return result;
  #print(result)     

async def aviation_mcp_call(
    tool_name:str,
    tool_args:dict = None
    ):
  tools = await client.get_tools()

  tool = next(
    t for t in tools
    if t.name == tool_name
  )

  result = await tool.ainvoke(
    tool_args or {}
  )

  return result

# Weather tool
weather_tool = None
forecast_tool = None


async def initialize_weather_tools():
  global weather_tool,forecast_tool

  if weather_tool is not None:
    return

  tools = await client.get_tools()

  weather_tool = next(
    t for t in tools
    if t.name == "get_curr_weather"
  )

  forecast_tool = next(
    t for t in tools
    if t.name == "get_forecast"
  )


async def weather_mcp_search(city: str):

  await initialize_weather_tools()

  return await weather_tool.ainvoke(
    {
      "city":city
    }
  )
    

async def forecast_mcp_search(city: str):
  await initialize_weather_tools()

  return await forecast_tool.ainvoke(
    {
      "city":city
    }
  )
# extract destination
 

def extract_destination(query: str) -> str:
    prompt = f"""
Extract only the destination city or country from the travel request.

Travel request:
{query}

Return only the destination name.
Do not add any explanation.
"""

    response = llm.invoke(prompt)

    destination = str(
        response.content
    ).strip()

    if not destination:
        raise ValueError(
            "The destination could not be extracted."
        )

    return destination