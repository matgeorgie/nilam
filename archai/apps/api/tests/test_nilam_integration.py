from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base, get_db
from app.main import app


def test_nilam_site_reference_is_saved_without_login(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'designs.db'}")
    Base.metadata.create_all(engine)

    def local_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = local_db
    try:
        with TestClient(app) as client:
            site = {
                'source': 'nilam', 'lat': 10.625455, 'lon': 76.311079,
                'district': 'Thrissur', 'suitability_percent': 87.5,
            }
            response = client.post('/api/projects', json={
                'name': 'Home in Thrissur',
                'specification': {
                    'site_context': site, 'plot_width': 30, 'plot_length': 40,
                    'shape': 'rectangle', 'floors': 1, 'road_location': 'south',
                    'rooms': [
                        {'type': 'bedroom', 'name': 'Bedroom 1'},
                        {'type': 'bedroom', 'name': 'Bedroom 2'},
                        {'type': 'living', 'name': 'Living'},
                        {'type': 'dining', 'name': 'Dining'},
                        {'type': 'kitchen', 'name': 'Kitchen'},
                        {'type': 'bathroom', 'name': 'Bathroom'},
                    ],
                },
            })
            assert response.status_code == 200, response.text
            project = response.json()
            assert project['specification']['site_context'] == site
            generated = client.post(f"/api/projects/{project['id']}/generate")
            assert generated.status_code == 200, generated.text
            assert generated.json()['layout']['rooms']
            assert generated.json()['specification']['site_context'] == site
            estimate = client.get(f"/api/projects/{project['id']}/estimate")
            assert estimate.status_code == 200, estimate.text
            assert estimate.json()['district'] == 'Thrissur'
            assert estimate.json()['district_source'] == 'nilam'
            assert estimate.json()['planning_budget_inr'] > estimate.json()['construction_inr']
            assert client.get(f"/api/projects/{project['id']}/estimate?district=Kochi").status_code == 422
            assert client.get(f"/api/projects/{project['id']}").json()['specification']['site_context'] == site
            assert any(item['id'] == project['id'] for item in client.get('/api/projects').json())
            assert client.post('/api/auth/login', json={}).status_code == 404
            invalid = client.post('/api/projects', json={'specification': {
                'site_context': {**site, 'lat': 42},
            }})
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
