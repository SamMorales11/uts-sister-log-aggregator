# tests/test_main.py (Versi Final dengan 7 Tes)

import os
import sys
import pytest
from fastapi.testclient import TestClient
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main import app

TEST_DB = "aggregator_test.db"

# Fixture yang sudah terbukti stabil
@pytest.fixture(scope="function")
def client():
    import src.main as main
    
    # Reset state sebelum setiap tes
    main.app_state["stats"] = {"received": 0, "unique_processed": 0, "duplicate_dropped": 0}
    
    # Inisialisasi app dan queue-nya sebelum diakses
    with TestClient(app) as test_client:
        # Kosongkan queue jika ada sisa dari tes sebelumnya yang gagal
        if hasattr(test_client.app.state, "event_queue"):
            queue = test_client.app.state.event_queue
            while not queue.empty():
                queue.get_nowait()

    main.DATABASE_FILE = TEST_DB
    
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    # TestClient akan menangani startup (termasuk init_db) dan shutdown aplikasi
    with TestClient(app) as test_client:
        yield test_client

# --- Kumpulan 7 Unit Test ---

# 5 Tes yang sudah berhasil sebelumnya
def test_publish_single_event(client: TestClient):
    event = {"topic": "test-topic", "eventId": "uuid-1", "timestamp": "2025-10-16T10:00:00Z", "source": "test-suite", "payload": {"data": "value1"}}
    response = client.post("/publish", json=event)
    assert response.status_code == 200
    time.sleep(1)
    response = client.get("/stats")
    stats = response.json()
    assert stats["unique_processed"] == 1
    assert stats["received"] == 1

def test_deduplication_logic(client: TestClient):
    event1 = {"topic": "system-logs", "eventId": "log-abc-123", "timestamp": "2025-10-16T11:00:00Z", "source": "app-server-1", "payload": {"msg": "User login success"}}
    event_duplicate = {"topic": "system-logs", "eventId": "log-abc-123", "timestamp": "2025-10-16T11:00:01Z", "source": "app-server-1", "payload": {"msg": "User login success"}}
    event2 = {"topic": "system-logs", "eventId": "log-def-456", "timestamp": "2025-10-16T11:00:02Z", "source": "app-server-2", "payload": {"msg": "DB query executed"}}
    client.post("/publish", json=[event1, event_duplicate, event2])
    time.sleep(1)
    response = client.get("/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["received"] == 3
    assert stats["unique_processed"] == 2
    assert stats["duplicate_dropped"] == 1

def test_get_events_endpoint(client: TestClient):
    event = {"topic": "metrics", "eventId": "metric-1", "timestamp": "2025-10-16T12:00:00Z", "source": "prometheus", "payload": {"cpu": 0.75}}
    client.post("/publish", json=event)
    time.sleep(1)
    response = client.get("/events?topic=metrics")
    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 1
    retrieved_event = data["events"][0]
    assert retrieved_event["event_id"] == "metric-1"

def test_schema_validation_bad_input(client: TestClient):
    bad_event = { "topic": "malformed-data", "timestamp": "2025-10-16T10:00:00Z", "source": "test-suite-bad", "payload": {"data": "value1"} }
    response = client.post("/publish", json=bad_event)
    assert response.status_code == 422

def test_large_batch_processing(client: TestClient):
    NUM_EVENTS = 100
    NUM_DUPLICATES = 20
    events = []
    for i in range(NUM_EVENTS):
        events.append({ "topic": "batch-test", "eventId": f"event-{i}", "timestamp": "2025-10-16T13:00:00Z", "source": "batch-sender", "payload": {"index": i} })
    events.extend(events[:NUM_DUPLICATES])
    response = client.post("/publish", json=events)
    assert response.status_code == 200
    time.sleep(3)
    response = client.get("/stats")
    stats = response.json()
    assert stats["received"] == NUM_EVENTS + NUM_DUPLICATES
    assert stats["unique_processed"] == NUM_EVENTS
    assert stats["duplicate_dropped"] == NUM_DUPLICATES

# --- 2 Tes Baru yang Ditambahkan dengan Super Hati-Hati ---

def test_get_events_for_empty_topic(client: TestClient):
    """
    Tes #6: Memastikan GET /events mengembalikan list kosong untuk topic yang tidak ada.
    """
    response = client.get("/events?topic=non-existent-topic")
    
    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "non-existent-topic"
    assert data["events"] == [] # Harus mengembalikan list kosong, bukan error

def test_publish_event_with_empty_payload(client: TestClient):
    """
    Tes #7: Memastikan event dengan payload object kosong {} tetap valid.
    """
    event = {
        "topic": "empty-payload-test",
        "eventId": "empty-payload-1",
        "timestamp": "2025-10-16T14:00:00Z",
        "source": "test-suite-empty",
        "payload": {} # Payload kosong
    }
    
    response = client.post("/publish", json=event)
    assert response.status_code == 200

    time.sleep(1) # Beri waktu untuk worker

    # Cek apakah event tersebut berhasil diproses
    response = client.get("/stats")
    stats = response.json()
    assert stats["unique_processed"] == 1
    assert stats["received"] == 1