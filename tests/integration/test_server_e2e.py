from fastapi.testclient import TestClient

from app.fast_api_app import app


client = TestClient(app)


def test_feedback_endpoint_accepts_structured_feedback() -> None:
    response = client.post(
        "/feedback",
        json={
            "score": 4,
            "user_id": "user-1",
            "session_id": "session-1",
            "text": "clear result",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
