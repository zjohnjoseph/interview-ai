from httpx import AsyncClient

_PYTHON_Q = {
    "text": "Explain the difference between a list and a tuple in Python with examples.",
    "domain": "python",
    "difficulty": "easy",
    "reference_answer": "Lists are mutable and use square brackets; tuples are immutable and use parentheses.",
}


async def test_create_question(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/questions", json=_PYTHON_Q, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert "reference_answer" in data
    assert data["domain"] == "python"
    assert data["difficulty"] == "easy"


async def test_create_question_invalid_domain(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post(
        "/api/questions",
        json={**_PYTHON_Q, "domain": "javascript"},
        headers=auth_headers,
    )
    assert r.status_code == 422


async def test_list_questions_filter_domain(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for _ in range(2):
        await client.post("/api/questions", json=_PYTHON_Q, headers=auth_headers)

    await client.post(
        "/api/questions",
        json={
            "text": "Write a SQL query to find duplicate rows in a table using GROUP BY.",
            "domain": "sql",
            "difficulty": "medium",
            "reference_answer": "SELECT col, COUNT(*) FROM t GROUP BY col HAVING COUNT(*) > 1.",
        },
        headers=auth_headers,
    )

    r = await client.get("/api/questions?domain=sql", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["domain"] == "sql"


async def test_list_questions_pagination(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    for _ in range(5):
        await client.post("/api/questions", json=_PYTHON_Q, headers=auth_headers)

    r = await client.get("/api/questions?limit=2", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_question_semantic_search(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    # RAG is mocked offline (hybrid_search → []), so we assert the contract:
    # an authenticated query returns 200 and a list of results.
    r = await client.get(
        "/api/questions/search?q=python%20decorators", headers=auth_headers
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)
