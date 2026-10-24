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

# CHANGED: new function names from mcp_client
from mcp_client import (
    tavily_mcp_search,
    aviation_airports_and_airlines,
    extract_destination,
    weather_and_forecast,
)

def get_database_url():
  database_url = os.getenv("DATABASE_URL")
  if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set.")

  if "sslmode" not in database_url:
    separator = "&" if "?" in database_url else "?"
    database_url += f"{separator}sslmode=require"

  return database_url  

url = get_database_url()
# CHANGED: removed print of DB url (it leaked the password into logs)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")


llm = ChatGroq(
   model = "openai/gpt-oss-120b",
   api_key = GROQ_API_KEY
)


# NEW: helper to keep prompts under the Groq TPM limit
def clip(value, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


class TravelState(TypedDict):
    message: Annotated[list[AnyMessage],operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: Annotated[int, operator.add]
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


# CHANGED: try/except added
def hotel_agent(state: TravelState) -> TravelState:
    query = f"Best hotels for {state['user_query']}"

    try:
        hotel_results = str(asyncio.run(tavily_mcp_search(query)))[:2500]
    except Exception as e:
        print(f"Hotel agent error: {e!r}")
        hotel_results = "Hotel information is currently unavailable."

    return {
        "hotel_results": hotel_results,
        "message": [
            AIMessage(content="Hotel search completed.")
        ],
        "llm_calls": 1
    }



# Flight Agent 
# CHANGED: single asyncio.run for both calls, content= typo fixed, airlines variable fixed
def flight_agent(state:TravelState):
   print("\nINSIDE FLIGHT AGENT\n")

   query = state["user_query"]

   try:
      airports, airlines = asyncio.run(aviation_airports_and_airlines())

      prompt = FLIGHT_AGENT_PROMPT.format(
         query=query,
         airport_data=str(airports)[:3000],
         airline_data=str(airlines)[:1500]
      )

      response = llm.invoke([
         SystemMessage(
            content = "You are an expert travel flight Planner."
         ),
         HumanMessage(content=prompt)
      ])

      flight_data = response.content

   except Exception as e:
       print(f"Flight agent error: {e!r}")
       flight_data = "Flight information is currently unavailable."

   return {
        "flight_results": flight_data,
        "message": [
            AIMessage(content=f"Flight search results: {flight_data}")
        ],
        "llm_calls": 1
    }

 # weather agent
# CHANGED: one asyncio.run for both calls, try/except, clipped output
def weather_agent(state:TravelState):
   try:
      city = extract_destination(state["user_query"])
      weather_data, forecast_data = asyncio.run(weather_and_forecast(city))
      weather_text = (
         f"Current Weather:\n{clip(weather_data, 1200)}\n\n"
         f"Forecast:\n{clip(forecast_data, 1800)}"
      )
   except Exception as e:
      print(f"Weather agent error: {e!r}")
      weather_text = "Weather information is currently unavailable."

   return {
      "weather_results": weather_text,
      "message":[
         AIMessage(
            content="Weather information fetched"
         )
      ]
   }


# REMOVED: itinerary_agent (final_agent already writes the day-by-day itinerary,
# so this was a duplicate LLM call that burned tokens and latency)


# CHANGED: inputs clipped, Itinerary block removed from prompt
def final_agent(state: TravelState):
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Flights:
{clip(state['flight_results'], 1500)}

Hotels:
{clip(state['hotel_results'], 2000)}

Weather:
{clip(state['weather_results'], 2500)}

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
- Make the itinerary practical, budget-aware, and easy to follow.
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
        "llm_calls": 1
    }



def aggregate_results(state: TravelState) -> TravelState:
    return {}


graph = StateGraph(TravelState)


graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("weather_agent", weather_agent)
graph.add_node("final_agent", final_agent)

# New aggregator node
graph.add_node("aggregate_results", aggregate_results)


graph.add_edge(START, "flight_agent")
graph.add_edge(START, "hotel_agent")
graph.add_edge(START, "weather_agent")


graph.add_edge("flight_agent", "aggregate_results")
graph.add_edge("hotel_agent", "aggregate_results")
graph.add_edge("weather_agent", "aggregate_results")

# CHANGED: aggregate goes straight to final_agent
graph.add_edge("aggregate_results", "final_agent")
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

# =========================
# Follow-up chat on a saved trip
# =========================

def chat_about_trip(question: str, thread_id: str, history: list | None = None):
    config = {"configurable": {"thread_id": thread_id}}
    saved = travel_graph.get_state(config).values

    if not saved or not saved.get("itinerary"):
        return {
            "thread_id": thread_id,
            "answer": "Is trip ka saved plan nahi mila. Pehle trip plan karo."
        }

    system_prompt = f"""You are a helpful travel assistant answering follow-up questions about ONE trip.
Use only the trip data below. If the answer is not in it, say so and give a short general suggestion.

Trip request:
{clip(saved.get('user_query', ''), 500)}

Flights:
{clip(saved.get('flight_results', ''), 1000)}

Hotels:
{clip(saved.get('hotel_results', ''), 1500)}

Weather:
{clip(saved.get('weather_results', ''), 1500)}

Final plan:
{clip(saved.get('itinerary', ''), 4000)}
"""

    messages = [SystemMessage(content=system_prompt)]

    for item in (history or [])[-6:]:
        text = clip(item.get("content", ""), 500)
        if item.get("role") == "user":
            messages.append(HumanMessage(content=text))
        else:
            messages.append(AIMessage(content=text))

    messages.append(HumanMessage(content=question))

    try:
        response = llm.invoke(messages)
        answer = response.content
    except Exception as e:
        print(f"Chat error: {e!r}")
        answer = "Abhi jawab nahi de paaya, thodi der baad dobara try karo."

    return {"thread_id": thread_id, "answer": answer}