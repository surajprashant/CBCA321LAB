"""End-to-end tests through the HTTP layer (Flask test client)."""
import subprocess

import pytest


@pytest.fixture
def repo_id(client, sample_repo):
    res = client.post("/api/repos", json={"source": str(sample_repo)})
    assert res.status_code == 201
    return res.get_json()["repository"]["id"]


def test_list_starts_empty(client):
    assert client.get("/api/repos").get_json() == []


def test_import_then_list(client, repo_id):
    repos = client.get("/api/repos").get_json()
    assert len(repos) == 1 and repos[0]["id"] == repo_id and repos[0]["commit_count"] == 6


def test_reimport_returns_200(client, repo_id, sample_repo):
    res = client.post("/api/repos", json={"source": str(sample_repo)})
    assert res.status_code == 200 and res.get_json()["created"] is False


@pytest.mark.parametrize("body", [None, {}, {"source": ""}, {"source": 42}])
def test_import_requires_source(client, body):
    res = client.post("/api/repos", json=body) if body is not None else client.post("/api/repos")
    assert res.status_code == 400 and "error" in res.get_json()


def test_import_bad_path_is_400(client, tmp_path):
    res = client.post("/api/repos", json={"source": str(tmp_path / "missing")})
    assert res.status_code == 400
    assert "Folder not found" in res.get_json()["error"]


def test_summary_endpoint(client, repo_id):
    data = client.get(f"/api/repos/{repo_id}/summary").get_json()
    assert data["commits"] == 6 and data["bus_factor"] == 1


def test_summary_with_filters(client, repo_id):
    data = client.get(f"/api/repos/{repo_id}/summary?since=2026-01-10&until=2026-01-31").get_json()
    assert data["commits"] == 3


def test_bad_date_is_400(client, repo_id):
    res = client.get(f"/api/repos/{repo_id}/summary?since=yesterday")
    assert res.status_code == 400 and "YYYY-MM-DD" in res.get_json()["error"]


def test_contributors_endpoint_and_sort(client, repo_id):
    rows = client.get(f"/api/repos/{repo_id}/contributors?sort=name").get_json()
    assert [r["name"] for r in rows] == ["Alice Smith", "Bob", "Carol"]
    assert client.get(f"/api/repos/{repo_id}/contributors?sort=evil").status_code == 400


def test_timeline_endpoint(client, repo_id):
    data = client.get(f"/api/repos/{repo_id}/timeline?granularity=week&top=2").get_json()
    assert len(data["labels"]) == 5 and len(data["series"]) == 3
    assert client.get(f"/api/repos/{repo_id}/timeline?top=abc").status_code == 400


def test_heatmap_endpoint(client, repo_id):
    data = client.get(f"/api/repos/{repo_id}/heatmap").get_json()
    assert len(data["matrix"]) == 7 and data["max"] == 1


def test_contributor_detail_endpoint(client, repo_id):
    cid = client.get(f"/api/repos/{repo_id}/contributors").get_json()[0]["contributor_id"]
    data = client.get(f"/api/repos/{repo_id}/contributors/{cid}").get_json()
    assert data["contributor"]["name"] == "Alice Smith"
    assert client.get(f"/api/repos/{repo_id}/contributors/9999").status_code == 404


def test_export_csv_endpoint(client, repo_id):
    res = client.get(f"/api/repos/{repo_id}/export.csv")
    assert res.status_code == 200 and res.mimetype == "text/csv"
    assert "attachment" in res.headers["Content-Disposition"]
    assert res.get_data(as_text=True).count("\n") == 4


def test_refresh_endpoint(client, repo_id, sample_repo):
    (sample_repo / "new.txt").write_text("hello\n")
    subprocess.run(["git", "add", "new.txt"], cwd=sample_repo, check=True)
    subprocess.run(["git", "-c", "user.name=Dan", "-c", "user.email=dan@x", "commit", "-q",
                    "-m", "new"], cwd=sample_repo, check=True)
    data = client.post(f"/api/repos/{repo_id}/refresh").get_json()
    assert data["new_commits"] == 1 and data["repository"]["contributor_count"] == 4


def test_delete_endpoint(client, repo_id):
    assert client.delete(f"/api/repos/{repo_id}").status_code == 204
    assert client.get(f"/api/repos/{repo_id}").status_code == 404
    assert client.delete(f"/api/repos/{repo_id}").status_code == 404


def test_unknown_repo_is_404_json(client):
    res = client.get("/api/repos/123/summary")
    assert res.status_code == 404 and res.get_json()["error"] == "Repository not found"


def test_pages_render(client, repo_id):
    assert client.get("/").status_code == 200
    page = client.get(f"/repos/{repo_id}")
    assert page.status_code == 200 and b"sample" in page.data
    cid = client.get(f"/api/repos/{repo_id}/contributors").get_json()[0]["contributor_id"]
    assert client.get(f"/repos/{repo_id}/contributors/{cid}").status_code == 200
    assert client.get("/repos/999").status_code == 404
    assert client.get(f"/repos/{repo_id}/contributors/999").status_code == 404
