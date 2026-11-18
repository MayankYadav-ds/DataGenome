async def authenticate_async(client):
    response = await client.post("/api/v1/auth/guest")
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def authenticate(client):
    response = client.post("/api/v1/auth/guest")
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
