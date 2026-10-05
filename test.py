from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights


# res = tavily_search("best travel destinations in Europe")
# print(res)

res = search_flights("Plan a 7 days Nepal trip from INDIA")
print(res)