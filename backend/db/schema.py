
from datetime import datetime
from typing import List, Optional
import uuid
from enum import Enum
from sqlmodel import Field, Relationship, SQLModel


def now() -> datetime:
    return datetime.now(datetime.timezone.utc)

# Enums
class ProductCategory(str, Enum):
    FOOD = "food"
    LADOOS = "ladoos"
    CHOCO = "choco"
    ARTS = "arts"
    OTHER = "other"


class OrderStatus(str, Enum):
    CREATED = "created"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FULFILLED = "fulfilled"


class PaymentStatus(str, Enum):
    INIT = "init"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class CredentialType(str, Enum):
    PASSWORD = "password"
    OAUTH = "oauth"


class AuthMethod(str, Enum):
    PHONE = "phone"
    PASSWORD = "password"
    OAUTH = "oauth"



# class User(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     public_id: str = Field(default_factory=lambda: str(uuid.uuid4()), index=True, unique=True)
#     name: Optional[str] = Field(nullable=True)
#     email: Optional[str] = Field(nullable=True)
#     created_at: datetime = Field(default_factory=datetime.now)
#     updated_at: datetime = Field(default_factory=datetime.now)
#     deleted_at: Optional[datetime] = Field(default=None, nullable=True)


#     # relationships
#     phones: List["UserPhone"] = Relationship(back_populates="user")
#     credentials: List["Credential"] = Relationship(back_populates="user")
#     addresses: List["Address"] = Relationship(back_populates="user")
#     carts: List["Cart"] = Relationship(back_populates="user")
#     orders: List["Order"] = Relationship(back_populates="user")
#     device_sessions: List["DeviceSession"] = Relationship(back_populates="user")
#     wishlists: List["Wishlist"] = Relationship(back_populates="user")

# class UserPhone(SQLModel, table=True):
#     """Allow only one phone for now and store verification metadata"""
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: int = Field(foreign_key="user.id", index=True,ondelete="CASCADE")
#     phone: str = Field(index=True)
#     is_primary: bool = Field(default=False)
#     verified_at: Optional[datetime] = Field(default=None, nullable=True)
#     created_at: datetime = Field(default_factory=datetime.now)

#     user: "User" = Relationship(back_populates="phones")

# # When user logs in attach user id to device session and also add refresh token with expiry .
# class DeviceSession(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)

#     # device identity (always present once session created)
#     session_token_hash: str = Field(index=True, nullable=False)   # hash of guest token

#     # auth refresh token (present only after login on this device)
#     refresh_token_hash: Optional[str] = Field(index=True, nullable=True)

#     user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)

#     device_name: Optional[str] = None
#     device_fingerprint: Optional[str] = None
#     ip_first_seen: Optional[str] = None
#     last_seen_ip: Optional[str] = None

#     # expiry & revocation
#     session_expires_at: Optional[datetime] = None   # guest session TTL
#     refresh_expires_at: Optional[datetime] = None   # refresh token TTL
#     refresh_revoked_at: Optional[datetime] = None

#     trusted: bool = False
#     created_at: datetime = Field(default_factory=datetime.now(datetime.timezone.utc))
#     last_seen_at: datetime = Field(default_factory=datetime.now)

# class Credential(SQLModel, table=True):
#     """Holds password hashes and oauth provider ids. Per-device refresh token hashes live in DeviceSession."""
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: int = Field(foreign_key="user.id", index=True)
#     type: CredentialType = Field(default=None,nullable=True)
#     provider: Optional[str] = None # e.g., 'google'
#     provider_user_id: Optional[str] = None
#     password_hash: Optional[str] = None # Argon2id/BCrypt hash
#     created_at: datetime = Field(default_factory=datetime.now)
#     revoked_at: Optional[datetime] = Field(default=None, nullable=True)


#     user: User = Relationship(back_populates="credentials")

# # Permissions (app-level, not DB):
# # Only users with role = 'admin' or role = 'vendor' and owner_id == user.id may edit/delete.
# class Product(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     public_id: str = Field(default_factory=lambda: str(uuid.uuid4()), index=True, unique=True)
#     sku: Optional[str] = Field(index=True, nullable=True)
#     name: str
#     description: Optional[str]
#     category: ProductCategory = Field(default=ProductCategory.OTHER)
#     base_price: int = 0 # paise
#     active: bool = True
#     created_at: datetime = Field(default_factory=datetime.now)
#     updated_at: datetime = Field(default_factory=datetime.now)

#     owner_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
#     # created_by/last_updated_by audit fields also useful
#     created_by: Optional[int] = Field(foreign_key="user.id", nullable=True)
#     updated_by: Optional[int] = Field(foreign_key="user.id", nullable=True)


#     images: List["ProductImage"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
#     # price_options: List["PriceOption"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


# class ProductImage(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     product_id: int = Field(foreign_key="product.id", index=True)
#     url: str
#     alt_text: Optional[str] = None
#     order: int = 0


#     product: Product = Relationship(back_populates="images")


# class PriceOption(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     product_id: int = Field(foreign_key="product.id", index=True)
#     label: str = Field(default="base") # 'base' | 'premium'
#     amount: int = Field(default=0) # paise
#     active: bool = True


#     product: Product = Relationship(back_populates="price_options")


# # CARTS — Persist carts server-side (DB/Redis) so they survive page reloads and can merge on login
# class Cart(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
#     session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
#     userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True)
#     abandoned_at: Optional[datetime] = None # set when inactive for TTL-based cleanup
#     created_at: datetime = Field(default_factory=datetime.now)
#     updated_at: datetime = Field(default_factory=datetime.now)

#     user: Optional[User] = Relationship(back_populates="carts")
#     items: List["CartItem"] = Relationship(back_populates="cart", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

# class CartItem(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     cart_id: int = Field(foreign_key="cart.id", index=True)
#     product_id: int = Field(foreign_key="product.id", index=True)
#     # price_option_id: Optional[int] = Field(foreign_key="priceoption.id", nullable=True)
#     quantity: int = Field(default=1)
#     unit_price_snapshot: Optional[int] = None # paise
#     created_at: datetime = Field(default_factory=datetime.now)
#     deleted_at: Optional[datetime] = None


#     cart: "Cart" = Relationship(back_populates="items")

# WISHLISTS — Persisted like carts; typically no TTL
# class Wishlist(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
#     session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
#     userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True)
#     name: Optional[str] = Field(default="Default")
#     created_at: datetime = Field(default_factory=datetime.now)
#     deleted_at: Optional[datetime] = None


#     user: User = Relationship(back_populates="wishlists")
#     items: List["WishlistItem"] = Relationship(back_populates="wishlist", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

# class WishlistItem(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     wishlist_id: int = Field(foreign_key="wishlist.id", index=True)
#     product_id: int = Field(foreign_key="product.id", index=True)
#     created_at: datetime = Field(default_factory=datetime.now)


#     wishlist: Wishlist = Relationship(back_populates="items")



# class Order(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     public_id: str = Field(default_factory=lambda: str(uuid.uuid4()), index=True, unique=True)
#     user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
#     session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
#     userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True) 

#     # totals
#     total_amount: int = Field(default=0) # paise
#     shipping_amount: int = Field(default=0)
#     status: OrderStatus = Field(default=OrderStatus.CREATED)


#     # snapshot contact & address (immutable for this order)
#     shipping_name: Optional[str]
#     shipping_phone: Optional[str]
#     shipping_email: Optional[str]
#     shipping_address_text: Optional[str]
#     shipping_address_id: Optional[int] = Field(foreign_key="address.id", index=True, nullable=True) # optional reference for convenience; do NOT rely on it alone


#     created_at: datetime = Field(default_factory=datetime.now)
#     updated_at: datetime = Field(default_factory=datetime.now)


#     items: List["OrderItem"] = Relationship(back_populates="order", sa_relationship_kwargs={"cascade": "all, delete-orphan"})




# class OrderItem(SQLModel, table=True):
#     """We keep FKs for traceability, but also snapshot name/price/labels because products & price options change over time."""
#     id: Optional[int] = Field(default=None, primary_key=True)
#     order_id: int = Field(foreign_key="order.id", index=True)
#     product_id: int = Field(foreign_key="product.id", index=True)
#     price_option_id: Optional[int] = Field(foreign_key="priceoption.id", nullable=True)


#     # immutable snapshots
#     product_name: str
#     # price_option_label: Optional[str] = None
#     unit_price: int = Field(default=0) # paise snapshot
#     quantity: int = Field(default=1)
    
#     order: "Order" = Relationship(back_populates="items")


# class Address(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
#     userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True) 
#     line1: str
#     line2: Optional[str] = None
#     city: str
#     state: Optional[str] = None
#     postal_code: str
#     country: str = Field(default="IN")
#     phone: Optional[str] = None
#     is_default: bool = Field(default=False)
#     created_at: datetime = Field(default_factory=datetime)
#     deleted_at: Optional[datetime] = Field(default=None, nullable=True)

#     user: Optional[User] = Relationship(back_populates="addresses")

# class OTPRequest(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     phone: str = Field(index=True)
#     code_hash: str  # store only hashed OTP
#     session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
#     created_at: datetime = Field(default_factory=datetime.now)
#     expires_at: datetime = Field(default_factory=lambda: datetime.now() + datetime.timedelta(minutes=5))
#     attempts: int = Field(default=0)
#     verified: bool = Field(default=False)

# class Payment(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     order_id: int = Field(foreign_key="order.id", index=True)
#     gateway: str
#     gateway_transaction_id: Optional[str] = Field(index=True, nullable=True)
#     amount: int = Field(default=0)
#     status: PaymentStatus = Field(default=PaymentStatus.INIT)
#     raw_payload: Optional[str] = None
#     created_at: datetime = Field(default_factory=datetime.now)
#     updated_at: datetime = Field(default_factory=datetime.now)


# fix necessary relationships 
# add cascades where necessary 
# products are for admin user so we can connect user id in products , just only allow admin  to edit them .
# add deleted at where necessary 
# add public uuids where necessary for security .
# what about order idempotency , also will payment idempotency will it use the same i key used for order ?

