# src/main.py (Versi Final Pamungkas)

import asyncio
import aiosqlite
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, Body, Request
from pydantic import BaseModel, Field

DATABASE_FILE = "aggregator.db"
# Hapus inisialisasi queue dari sini
# event_queue = asyncio.Queue() 

app_state = { "start_time": time.time(), "stats": { "received": 0, "unique_processed": 0, "duplicate_dropped": 0 } }

class Event(BaseModel):
    topic: str
    event_id: str = Field(..., alias="eventId")
    timestamp: datetime
    source: str
    payload: Dict[str, Any]

async def init_db():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("PRAGMA journal_mode=WAL;") # Performa lebih baik untuk concurrent read/write
        await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT NOT NULL, event_id TEXT NOT NULL,
                timestamp DATETIME NOT NULL, source TEXT NOT NULL, payload_json TEXT
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dedup_keys (
                topic TEXT NOT NULL, event_id TEXT NOT NULL, PRIMARY KEY (topic, event_id)
            )""")
        await db.commit()
    print(f"Database '{DATABASE_FILE}' initialized successfully.")

async def consumer_worker(queue: asyncio.Queue):
    print("Consumer worker started.")
    while True:
        event = await queue.get()
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                try:
                    await db.execute("INSERT INTO dedup_keys (topic, event_id) VALUES (?, ?)", (event.topic, event.event_id))
                    payload_str = json.dumps(event.payload)
                    await db.execute(
                        "INSERT INTO processed_events (topic, event_id, timestamp, source, payload_json) VALUES (?, ?, ?, ?, ?)",
                        (event.topic, event.event_id, event.timestamp, event.source, payload_str))
                    await db.commit()
                    app_state["stats"]["unique_processed"] += 1
                except aiosqlite.IntegrityError:
                    app_state["stats"]["duplicate_dropped"] += 1
        except asyncio.CancelledError:
            print("Worker is shutting down.")
            break
        except Exception as e:
            print(f"An unexpected error in worker: {e}")
        finally:
            queue.task_done()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application starting up...")
    # Buat queue di dalam lifespan agar terikat pada event loop yang benar
    queue = asyncio.Queue()
    app.state.event_queue = queue
    
    await init_db()
    
    app.state.worker_task = asyncio.create_task(consumer_worker(queue))
    yield
    print("Application shutting down...")
    app.state.worker_task.cancel()
    try:
        await app.state.worker_task
    except asyncio.CancelledError:
        print("Worker task cancelled successfully.")

app = FastAPI(lifespan=lifespan)

@app.post("/publish")
async def publish_events(request: Request, events: List[Event] | Event = Body(...)):
    if not isinstance(events, list):
        events = [events]
    for event in events:
        await request.app.state.event_queue.put(event)
        app_state["stats"]["received"] += 1
    return {"status": "ok", "ingested_count": len(events)}

@app.get("/events")
async def get_events(request: Request, topic: str):
    events = []
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT topic, event_id, timestamp, source, payload_json FROM processed_events WHERE topic = ?", (topic,)) as cursor:
            async for row in cursor:
                event_data = dict(row)
                event_data["payload"] = json.loads(event_data.pop("payload_json"))
                events.append(event_data)
    return {"topic": topic, "events": events}

@app.get("/stats")
async def get_stats(request: Request):
    uptime_seconds = time.time() - app_state["start_time"]
    topics_count = 0
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute("SELECT COUNT(DISTINCT topic) FROM processed_events") as cursor:
            result = await cursor.fetchone()
            if result:
                topics_count = result[0]
    return {
        "uptime": f"{uptime_seconds:.2f} seconds",
        **app_state["stats"],
        "topics_count": topics_count,
        "queue_size": request.app.state.event_queue.qsize()
    }