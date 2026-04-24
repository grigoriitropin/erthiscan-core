import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.integration
def test_companies_list():
    resp = client.get("/companies")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "pages" in data


@pytest.mark.integration
def test_company_not_found():
    resp = client.get("/companies/0")
    assert resp.status_code == 404


@pytest.mark.integration
def test_companies_pagination():
    resp = client.get("/companies?page=1&per_page=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["per_page"] == 10


@pytest.mark.integration
def test_companies_search():
    resp = client.get("/companies?search=test")
    assert resp.status_code == 200


@pytest.mark.integration
def test_companies_sort_score():
    resp = client.get("/companies?sort=score_desc")
    assert resp.status_code == 200


@pytest.mark.integration
def test_companies_sort_name():
    resp = client.get("/companies?sort=name_asc")
    assert resp.status_code == 200
