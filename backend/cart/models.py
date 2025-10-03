


from pydantic import BaseModel


class CartItemInput(BaseModel):
    product_id: int
    quantity: int = 1