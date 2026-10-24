from pathlib import Path
import traceback

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# CHANGED: chat_about_trip imported along with run_travel_agent
from backend import run_travel_agent, chat_about_trip

# This is kept from the original project to allow the existing synchronous
# agent functions to call async MCP helpers inside FastAPI.
import nest_asyncio

nest_asyncio.apply()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Way-wise-AI",
    description="LangGraph Multi-Agent Travel Planner with trip chat and FastAPI frontend",
    version="2.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None


# NEW: request body for follow-up chat
class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    history: list[dict] = []


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


# CHANGED: plain `def` (was `async def`) so the long blocking agent run
# executes in a worker thread and does not freeze the whole server.
@app.post("/api/travel")
def travel_planner(request_data: TravelRequest):
    try:
        user_message = request_data.message.strip()

        if not user_message:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty.",
                },
            )

        result = run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id,
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
            }
        )

    except Exception as exc:
        print("ERROR:", exc)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(exc),
            },
        )


# NEW: follow-up chat on an already planned trip (one LLM call, no graph re-run)
@app.post("/api/chat")
def chat(request_data: ChatRequest):
    try:
        result = chat_about_trip(
            question=request_data.question,
            thread_id=request_data.thread_id,
            history=request_data.history,
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
            }
        )

    except Exception as exc:
        print("CHAT ERROR:", exc)
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(exc),
            },
        )


# REMOVED: /api/travel/approve (backend has no human-in-the-loop step)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "Way-wise-AI API is running",
        "features": [
            "parallel_agents",
            "trip_chat",
        ],
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )