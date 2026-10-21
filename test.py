import asyncio
from mcp_client import get_all_tools

if __name__ == "__main__":
  query = "latest news about ai"
  asyncio.run(get_all_tools())