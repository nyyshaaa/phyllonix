
import pytest
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from backend.main import app

url_prefix = "/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_create_protein_ladoo_product(ac_client):
    
    headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTk5NTIzYS02NDc5LTdkZWUtOTRkNy02NjdjZTU1Yjg1MmUiLCJpYXQiOjE3NTkwODEwOTAsImV4cCI6MTc1OTA4NDY5MCwianRpIjoiYmM5NDljM2ZmZDc1NDA2MzQ0Nzk3YWUzMzBkYmYzZDRmN2M0NDMxYzAxZDBiYWU4N2JiNjI3YzMyNGM5ZmFmNSIsInJvbGVzIjpbNF0sInJvbGVfdmVyc2lvbiI6MH0.AgFKXvUywQa2w1Ngzeb7148WL08HiXgEtqTDm8zZddk"}
    
    product_data = {
        "name": "Hemp & Sesame Ladoo",
        "description": "Nutritious protein-rich ladoo made with hemp seeds, chia seeds, sesame seeds, jaggery, ghee, and cacao. Perfect for energy and strength building.",
        "base_price": 500,  
        "stock_qty": 25,
        "specs": {
            "ingredients": {
                "primary": ["hemp seeds", "chia seeds", "sesame seeds"],
                "sweetener": "jaggery",
                "fat": "ghee (30%)",
                "flavoring": "cacao (5%)",
                "sugar":"8%"
            },
            "nutritional_info": {
                "protein_content": "high",
                "energy_boost": True,
                "strength_building": True,
                "natural_ingredients": True,
                "sugar(jaggery)":"8g/100g"
            },
            "dietary_info": {
                "vegetarian": True,
                "vegan": False,  
                "gluten_free": True
            },
            "storage": {
                "shelf_life": "120 days",
                "storage_condition": "cool, dry place"
            },
            "weight": "50g per piece",
            "pieces_per_pack": 6
        },
        "category_ids": [2,3]
    }
    
    response = await ac_client.post(
        "/api/v1/admin/products/",
        json=product_data,
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    product = data["product"]
    
    
    assert product["name"] == "Hemp & Sesame Ladoo"

