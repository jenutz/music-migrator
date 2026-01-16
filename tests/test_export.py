"""Exporting an imported playlist into a target on either service."""


def test_export_creates_a_target_playlist(client, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})

    response = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    )

    assert response.status_code == 200
    target = response.json()["playlist"]
    assert target["service"] == "yandex"
    assert target["kind"] == "target"
    assert target["source_playlist_id"] == youtube_import
    assert target["total"] == 1


def test_export_needs_a_token_on_the_destination(client, youtube_import):
    response = client.post(f"/api/export/{youtube_import}", json={"dst_service": "yandex"})

    assert response.status_code == 400
    assert "войдите" in response.json()["detail"].lower()


def test_export_to_the_same_service(client, fake, youtube_import):
    """A liked library has to become a playlist somewhere. Same service is fine."""
    client.post("/api/token/youtube", json={"value": "header-block"})
    response = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "youtube", "delivery": "playlist"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "youtube"
    assert body["delivery"] == "playlist"


def test_cannot_export_an_export(client, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]

    response = client.post(f"/api/export/{target_id}", json={"dst_service": "youtube"})
    assert response.status_code == 400


def test_migrate_page_opens_the_target_playlist(client, youtube_import):
    client.post("/api/token/yandex", json={"value": "y0-token"})
    target_id = client.post(
        f"/api/export/{youtube_import}", json={"dst_service": "yandex"}
    ).json()["playlist_id"]

    response = client.get(f"/migrate/{target_id}")
    assert response.status_code == 200
    assert "YouTube Music" in response.text


def test_migrate_page_rejects_an_imported_playlist(client, youtube_import):
    assert client.get(f"/migrate/{youtube_import}").status_code == 400


def test_export_rejects_an_unknown_delivery(client, imported):
    client.post("/api/token/youtube", json={"value": "header-block"})
    response = client.post(
        f"/api/export/{imported[0]}", json={"dst_service": "youtube", "delivery": "telepathy"}
    )
    assert response.status_code == 400


def test_export_payload_carries_the_delivery(client, imported):
    client.post("/api/token/youtube", json={"value": "header-block"})
    target_id = client.post(
        f"/api/export/{imported[0]}", json={"dst_service": "youtube", "delivery": "playlist"}
    ).json()["playlist_id"]

    playlist = client.get(f"/api/playlist/{target_id}").json()["playlist"]
    assert playlist["delivery"] == "playlist"
    assert playlist["remote_playlist_id"] is None
