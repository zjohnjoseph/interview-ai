import fitz  # type: ignore[import]
from httpx import AsyncClient

_INTERVIEW = {
    "job_title": "Senior Python Developer",
    "job_description": (
        "We are building a high-scale distributed platform and need an experienced "
        "Python developer with strong backend and system design skills."
    ),
    "required_skills": "Python, FastAPI, PostgreSQL, Redis, system design",
    "role_level": "senior",
    "max_questions": 8,
}


def _make_test_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Senior Python Developer\nSkills: Python, FastAPI")
    return doc.tobytes()


async def _publish_interview(client: AsyncClient, headers: dict[str, str]) -> str:
    """Helper: create + publish an interview, return interview_id."""
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=headers)
    assert r.status_code == 201
    interview_id = r.json()["id"]
    r = await client.post(f"/api/interviews/{interview_id}/publish", headers=headers)
    assert r.status_code == 200
    return interview_id


async def test_create_interview(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "draft"
    assert data["job_title"] == _INTERVIEW["job_title"]
    assert data["role_level"] == "senior"
    assert data["max_questions"] == 8


async def test_list_interviews_only_own(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)

    r = await client.post(
        "/api/auth/signup",
        json={"email": "userb@example.com", "name": "User B", "password": "strongpass123"},
    )
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}
    await client.post(
        "/api/interviews",
        json={**_INTERVIEW, "job_title": "User B Position"},
        headers=headers_b,
    )

    r = await client.get("/api/interviews", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["job_title"] == _INTERVIEW["job_title"]


async def test_get_interview(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.get(f"/api/interviews/{interview_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == interview_id
    assert r.json()["job_title"] == _INTERVIEW["job_title"]


async def test_update_interview(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.patch(
        f"/api/interviews/{interview_id}",
        json={"job_title": "Updated Python Engineer"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["job_title"] == "Updated Python Engineer"
    assert data["role_level"] == "senior"  # unchanged


async def test_delete_interview_soft(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.delete(f"/api/interviews/{interview_id}", headers=auth_headers)
    assert r.status_code == 204

    r = await client.get(f"/api/interviews/{interview_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


async def test_publish_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "active"
    assert data["job_title"] == _INTERVIEW["job_title"]


async def test_publish_draft_only(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)
    assert r.status_code == 200

    r = await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)
    assert r.status_code == 400


async def test_update_active_interview_blocked(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]
    await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)

    r = await client.patch(
        f"/api/interviews/{interview_id}",
        json={"job_title": "Cannot Change This"},
        headers=auth_headers,
    )
    assert r.status_code == 400


async def test_other_user_gets_404(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.post(
        "/api/auth/signup",
        json={"email": "intruder@example.com", "name": "Intruder", "password": "strongpass123"},
    )
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get(f"/api/interviews/{interview_id}", headers=headers_b)
    assert r.status_code == 404


async def test_upload_candidate_resume(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    interview_id = await _publish_interview(client, auth_headers)

    r = await client.post(
        f"/api/interviews/{interview_id}/candidates",
        data={"candidate_name": "Alice Smith", "candidate_email": "alice@example.com"},
        files={"resume": ("cv.pdf", _make_test_pdf(), "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert "token" in data
    assert data["candidate_name"] == "Alice Smith"
    assert data["status"] == "pending"


async def test_upload_resume_before_publish(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]  # still draft

    r = await client.post(
        f"/api/interviews/{interview_id}/candidates",
        data={"candidate_name": "Alice", "candidate_email": "alice@example.com"},
        files={"resume": ("cv.pdf", _make_test_pdf(), "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 400


async def test_upload_non_pdf(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    interview_id = await _publish_interview(client, auth_headers)

    r = await client.post(
        f"/api/interviews/{interview_id}/candidates",
        data={"candidate_name": "Bob", "candidate_email": "bob@example.com"},
        files={"resume": ("cv.txt", b"This is not a PDF", "text/plain")},
        headers=auth_headers,
    )
    assert r.status_code == 400
