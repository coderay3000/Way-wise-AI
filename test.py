from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights
from backend import run_travel_agent

# res = tavily_search("best travel destinations in Europe")
# print(res)

# res = search_flights("Plan a 7 days Nepal trip from INDIA")
# print(res)

user_input = input("Enter your travel query: ")

response = run_travel_agent(
    user_input=user_input,
    thread_id="test_user"
)

print("\nFINAL RESPONSE:\n")
print(response["answer"])