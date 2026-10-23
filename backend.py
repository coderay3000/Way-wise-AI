import os
import certifi
import asyncio
from dotenv import load_dotenv

load_dotenv()

os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
os.environ["SSL_CERT_FILE"] = certifi.where()

from typing import TypedDict, Annotated
import operator
import uuid


import psycopg  #Psycopg Python ki ek PostgreSQL database adapter/library hai   Python application ↔ Psycopg ↔ PostgreSQL database
from psycopg.rows import dict_row

from langgraph.graph import StateGraph,START,END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.prompts import PromptTemplate 
from langchain_core.messages import (
    AnyMessage,
    SystemMessage,
    HumanMessage,
    AIMessage 
)
from langchain_groq import ChatGroq
#from tools.tavily_tool import tavily_search
#from tools.flight_tool import search_flights
from mcp_client import tavily_mcp_search,aviation_mcp_call,extract_destination,forecast_mcp_search,weather_mcp_search

def get_database_url():
  database_url = os.getenv("DATABASE_URL")
  if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set.")

  if "sslmode" not in database_url:
    separator = "&" if "?" in database_url else "?"
    database_url += f"{separator}sslmode=require"

  return database_url  

url = get_database_url()
print(f"Connecting to database at {url}")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")


llm = ChatGroq(
   model = "openai/gpt-oss-120b",
   api_key = GROQ_API_KEY
)

class TravelState(TypedDict):
    message: Annotated[list[AnyMessage],operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int
    weather_results:str


# def flight_agent(state: TravelState) -> TravelState:
#     query = state["user_query"]
#     flight_data = search_flights(query)

#     return {
#          "flight_results": flight_data,
#          "message": [
#             AIMessage(content=f"Flight search results: {flight_data}")
#          ],
#          "llm_calls": state.get("llm_calls", 0) + 1
           
#     }

# Flight tool router prompt

FLIGHT_AGENT_PROMPT = """
 You are a travel flight expert .

 User Query:
 {query}

 Airport Information
 {airport_data}

 Airline Information
 {airline_data}

 Generate:

 1.Likely departure airport
 2.Likely arrival airport
 3.Airline serving this route
 4.Typical flight duration
 5.Estimated airfare range 
 6.Peak season pricing warning
 7.Booking Advice

 Return concise  travel guidance.

"""


def hotel_agent(state: TravelState) -> TravelState:
    query = f"Best hotels for {state['user_query']}"

    hotel_results = asyncio.run(tavily_mcp_search(query))

    # Limit the search result size before passing it downstream
    hotel_results = str(hotel_results)[:2500]

    return {
        "hotel_results": hotel_results,
        "message": [
            AIMessage(content="Hotel search completed.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }



# Flight Agent 
def flight_agent(state:TravelState):
   print("\nINSIDE FLIGHT AGENT\n")

   query = state["user_query"]

   try:

      airports = asyncio.run(
         aviation_mcp_call(
            "list_airports"
         )
      )

      airlines = asyncio.run(
         aviation_mcp_call(
            "list_airlines"
         )
      )

      print("\nAIRPORTS:",airports)
      print("\nAirlines",airlines)

      prompt = FLIGHT_AGENT_PROMPT.format(
         query=query,
         airport_data=str(airports)[:3000],
         airline_data=str(airports)[:1500]
      )

      response = llm.invoke([
         SystemMessage(
            contents = "You are an expert travel flight Planner."
         ),
         HumanMessage(content=prompt)
      ])

      flight_data = response.content

   
   except Exception as e:
       print(f"Flight agent error: {e}")
       flight_data = "Flight information is currently unavailable."

   return {
        "flight_results": flight_data,
        "message": [
            AIMessage(content=f"Flight search results: {flight_data}")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }

 # weather agent
def weather_agent(state:TravelState):
   city=extract_destination(state["user_query"])

   weather_data=asyncio.run(
      weather_mcp_search(city)
   )  

   forecast_data=asyncio.run(
      forecast_mcp_search(city)
   )  

   return {
      "weather_results":f"""
       Current Weather:
       {weather_data}
       
       Forecast:
       {forecast_data}
     """,
     "message":[
        AIMessage(
           content="Weather information fetched"
        )
     ]
   }
 
   
def itinerary_agent(state: TravelState) -> TravelState:
   prompt = f"""Create a complete travel itinerary.
   
   User Query: {state['user_query']}
   
   Flight Results: {state['flight_results']}
   
   Hotel Results: {state['hotel_results']}

   Weather Results: {state['weather_results']}


  make the itinerary practical , budget-aware, and easy to follow.   
  """

   response = llm.invoke([
          SystemMessage(content="You are a travel assistant that creates detailed itineraries based on user queries and search results."),
          HumanMessage(content=prompt)
       ])
   return {
      "itinerary": response.content,
      "message":[response],
      "llm_calls": state.get("llm_calls", 0) + 1
   }

def final_agent(state: TravelState):
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{state['flight_results']}

Hotels:
{state['hotel_results']}

Weather:
{state['weather_results']}

Itinerary:
{state['itinerary']}

Format the final answer beautifully using these sections:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather Information
5. Day-by-Day Itinerary
6. Estimated Budget
7. Final Recommendations

Important:
- Be clear and practical.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Include Weather based travel Advice.
- Keep the response useful for real travel planning.
"""

    response = llm.invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])

    return {
       "itinerary": response.content,
        "message": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent",weather_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent",final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "weather_agent")
graph.add_edge("weather_agent","itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)


# =========================
# Function for FastAPI
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(
        {
            "message": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "itinerary": "",
            "llm_calls": 0
        },
        config=config
    )

    final_answer = result["message"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather_results": result.get("weather_results", ""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls", 0),
    }