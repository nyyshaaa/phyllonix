import enum
from sqlalchemy import ARRAY, JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint,BigInteger
from uuid6 import uuid7
from datetime import datetime
from typing import Any, Dict, List, Optional 
from sqlalchemy.dialects.postgresql import UUID,JSONB
from sqlalchemy.dialects.postgresql import INET
from sqlmodel import Column, SQLModel, Field, Relationship, String
from backend.common.utils import now

# Join tables
class UserRole(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True,nullable=False)
    #* add user_phone id as well later 
    role_id: Optional[int] = Field(default=None, foreign_key="role.id", index=True,nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role_user_id_role_id"),)


class Users(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)  #* optional just means for the created object before saving in db .
    public_id: uuid7 = Field(
        default_factory=uuid7, 
        sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
    )
    email: Optional[str] = Field(default=None,sa_column=Column(String(320), nullable=True,unique=True))  #* nullable allowed in case a user has only phone based account ,but usually email is necessary so make it non nullable later
    name: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    role_version:int=Field(default=0,nullable=False)
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))

    deleted_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True)))

    
    # relationships
    phones: List["UserPhone"] = Relationship(back_populates="user")   # user->userphone (1 to many)
    credentials: List["Credential"] = Relationship(back_populates="user")
    addresses: List["Address"] = Relationship(back_populates="user")
    session_tokens: List["DeviceAuthToken"] = Relationship(back_populates="user")
    roles: List["Role"] = Relationship(back_populates="user",link_model=UserRole)
    media:"UserMedia" = Relationship(back_populates="user")
    cart: "Cart" = Relationship(back_populates="users") # user -> cart (1:1)
    # orders: List["Order"] = Relationship(back_populates="user")

class UserMedia(SQLModel,table=True):
    id:Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(default=None, foreign_key="users.id", unique=True,nullable=False)
    # Simple profile images (with a single predefined size)
    profile_image_url: Optional[str] = Field(default=None, sa_column=Column(String(1024), nullable=True))
    profile_image_thumb_url: Optional[str] = Field(default=None, sa_column=Column(String(1024), nullable=True))
    
    user:"Users" = Relationship(back_populates="media")

class RolePermission(SQLModel, table=True):
    id:Optional[int] = Field(default=None, primary_key=True)
    role_id: int = Field(foreign_key="role.id", index=True,nullable=False)
    permission_id: int = Field(foreign_key="permission.id", index=True,nullable=False)

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission_role_id_permission_id"),)

# Core tables
class Role(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(length=200), unique=True, nullable=False,default='buyer'))
    description: Optional[str] = None
    user: List["Users"] = Relationship(back_populates="roles",link_model=UserRole)
    permissions: List["Permission"] = Relationship(back_populates="roles", link_model=RolePermission)

class Permission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, unique=True, nullable=False))
    description: Optional[str] = None
    roles: List["Role"] = Relationship(back_populates="permissions", link_model=RolePermission)

class UserPhone(SQLModel, table=True):
    """Allow only one phone for now and store verification metadata"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False))
    phone: str = Field(sa_column=Column(String(20),nullable=False,unique=True))
    is_primary: bool = Field(default=False)
    verified_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True), default=now,onupdate=now,nullable=False))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False,default=now))

    user: "Users" = Relationship(back_populates="phones") 

class CredentialType(str, enum.Enum):
    PASSWORD = "password"
    OAUTH = "oauth"


class Credential(SQLModel, table=True):
    """Holds password hashes and oauth provider ids. Per-device refresh token hashes live in DeviceSession."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"),
            index=True,nullable=False))
    type: CredentialType = Field(nullable=False) 
    provider: Optional[str] = Field(sa_column=Column(String(64), default=None, nullable=True))
    provider_user_id: Optional[str] = Field(default=None,sa_column=Column(String(255), nullable=True))
    provider_email: Optional[str] = Field(default=None,sa_column=Column(String(320), nullable=True))
    password_hash: Optional[str] = Field(sa_column=Column(Text(),nullable=True))
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now,nullable=False))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now,nullable=False, onupdate=now))
    revoked_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True))


    user: "Users" = Relationship(back_populates="credentials")  # every credential must be linked to user .


class Address(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
            nullable=False))
    line1: str
    line2: Optional[str] = None
    city: str
    state: Optional[str] = None
    name: Optional[str] = Field(sa_column=Column(String(128), nullable=True))
    postal_code: str
    country: str = Field(default="IN",nullable=False)
    phone: str = Field(nullable=False)
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))
    deleted_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True))

    user: "Users" = Relationship(back_populates="addresses")
    # phone: Optional["UserPhone"] = Relationship(back_populates="addresses")

class AuthMethod(str, enum.Enum):
    PASSWORD = "password"
    PHONE = "phone"
    OAUTH = "oauth"


class DeviceSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # hashed session token (e.g., sha256 hex = 64 chars) - unique so no duplicate tokens
    session_token_hash: str = Field(sa_column=Column(String(128), nullable=False, unique=True, index=True))
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"),
            index=True,nullable=True))

    # metadata...
    device_name: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    device_type: Optional[str] = Field(default=None, sa_column=Column(String(64)))
    user_agent_snippet: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    device_fingerprint_hash: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))

    ip_first_seen: Optional[str] = Field(default=None, sa_column=Column(INET, nullable=True))
    last_seen_ip: Optional[str] = Field(default=None, sa_column=Column(INET, nullable=True))

    last_activity_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))

    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    session_expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    # relationship to tokens (one-to-many)
    tokens: List["DeviceAuthToken"] = Relationship(back_populates="device_session",
                                                  sa_relationship_kwargs={"cascade": "all, delete-orphan"},
                                                  passive_deletes=True)


class DeviceAuthToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    device_session_id: int = Field(sa_column=Column(ForeignKey("devicesession.id", ondelete="CASCADE"), index=True, nullable=False))

    # canonical link to user 
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False))

    # hashed refresh token
    token_hash: str = Field(sa_column=Column(String(200), nullable=False, unique=True, index=True))

    issued_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    revoked_by: Optional[str] = Field(default=None, sa_column=Column(String(32), nullable=True))  # 'user'|'system'|'admin'
    revoked_reason: Optional[str] = Field(default=None, sa_column=Column(String(256), nullable=True))

    # auth_method stored as an enum column
    auth_method: AuthMethod = Field(sa_column=Column(Enum(AuthMethod, create_type=False), nullable=False))

    device_session: "DeviceSession" = Relationship(back_populates="tokens")
    user: "Users" = Relationship(back_populates="session_tokens")


# ---------------------------------------------------------------------------------------------------------

class ImageUploadStatus(str, enum.Enum):
    PENDING_UPLOADED = "pending_uploaded"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

class ProductCategoryLink(SQLModel, table=True):
   
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(sa_column=Column(ForeignKey("product.id", ondelete="CASCADE"), index=True, nullable=False))
    prod_category_id: int = Field(sa_column=Column(ForeignKey("productcategory.id", ondelete="CASCADE"), index=True, nullable=False))

    # unique constraint to avoid duplicate links
    __table_args__ = (
        UniqueConstraint("product_id", "prod_category_id", name="uq_product_category"),
    )


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: uuid7 = Field(
        default_factory=uuid7, 
        sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
    )
    stock_qty:int=Field(sa_column=Column(Integer(), nullable=False))
    sku: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True)) # keep nullable for now , later when necessary create index 
    name: str = Field(sa_column=Column(String(255), nullable=False,unique=True))
    description: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    base_price: int = Field(default=0,description="Price in paise (int)")

    specs: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Flexible product specs JSON (e.g. { 'weight_g': 500, 'flavor': 'saffron' })",
    )

    owner_id: Optional[int] = Field(sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True))
    # audit fields(in case admin creates  a product on behalf of sa seller)
    # created_by: Optional[int] = Field(foreign_key="user.id", nullable=True)
    # updated_by: Optional[int] = Field(foreign_key="user.id", nullable=True)

    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))

    deleted_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True)))


    images: List["ProductImage"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    prod_categories: List["ProductCategory"] = Relationship(back_populates="products", link_model=ProductCategoryLink)

    

    # price_options: List["PriceOption"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

# 1 image content id can belong to many product images
class ProductImage(SQLModel, table=True):

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(sa_column=Column(ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True))
    content_id: Optional[int] = Field(default=None, sa_column=Column(ForeignKey("imagecontent.id", ondelete="CASCADE"), nullable=True))
    
    public_id: uuid7 = Field(default_factory=uuid7, sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False))
    storage_key: str = Field(sa_column=Column(String(1024), nullable=True,unique=True), description="bucket key (not public URL)")
    storage_provider: str = Field(default="cloudinary", sa_column=Column(String(64), nullable=False))
    bucket: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    mime_type: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    file_size: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    
    variants: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB, nullable=True))
    status: ImageUploadStatus = Field(sa_column=Column(Enum(ImageUploadStatus, create_type=False),default=ImageUploadStatus.PENDING_UPLOADED,nullable=False))
    orig_filename: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    sort_order: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    alt_text: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))

    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    updated_at: datetime = Field(default_factory=now,sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))

    # uploaded_by: Optional[int] = Field(foreign_key="user.id", nullable=True)

    product: "Product" = Relationship(back_populates="images")
    img_content : "ImageContent" = Relationship(back_populates="product_imgs")

class ImageContent(SQLModel, table=True):
    """
    Canonical content rows keyed by checksum. Workers insert with ON CONFLICT DO NOTHING.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    checksum: str = Field(sa_column=Column(String(128), nullable=False, unique=True), description="sha256 hex")
    # owner_id: Optional[int] = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True))
    public_id:uuid7 = Field(default_factory=uuid7, sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False))
    provider_public_id: Optional[str] = Field(default=None, sa_column=Column(String(1024), nullable=True))
    url: Optional[str] = Field(default=None, sa_column=Column(String(2048), nullable=True))
    meta: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))

    product_imgs : List["ProductImage"] = Relationship(back_populates="img_content")


class ProductCategory(SQLModel, table=True):
   
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(200), unique=True, nullable=False))
    description: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    updated_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now, onupdate=now))

    products: List["Product"] = Relationship(back_populates="prod_categories", link_model=ProductCategoryLink)


class ProviderWebhookEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider_event_id: str = Field(sa_column=Column(String(1000), nullable=False,unique=True))  # provider unique id (asset_id or public_id:version)
    provider: str = Field(sa_column=Column(String(100), nullable=True))           # e.g. 'cloudinary'
    payload: dict = Field(sa_column=Column(JSONB, nullable=False))
    received_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    # processed: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    processed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    attempts: Optional[int] = Field(default=0, sa_column=Column(Integer, nullable=True))

#---------------------------------------------------------------------------------------------------------

class RoleAudit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_user_id:int = Field(sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    target_user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    old_roles: List[str] = Field(default_factory=list,sa_column=Column(ARRAY(String), nullable=False))
    new_roles: List[str] = Field(default_factory=list,sa_column=Column(ARRAY(String), nullable=False))
    reason: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    updated_at: datetime = Field(default_factory=now,sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))



#-----------------------------------------------------------------------------------------------------------

# CARTS — Persist carts server-side (DB/Redis) so they survive page reloads and can merge on login
# user / userphone to cart (1:1)
# hard delete cart items after some retention window when not used for a longgg time 
class Cart(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True,unique= True),
    )
    session_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("devicesession.id", ondelete="SET NULL"), nullable=True, index=True,unique=True),
    )
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    updated_at: datetime = Field(default_factory=now,sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))


    user: Optional["Users"] = Relationship(back_populates="cart")   # (guest cart)a cart may have no user 
    cart_items: List["CartItem"] = Relationship(back_populates="cart")

# set deleted_at when item is added to order , hard delete after some time .
# CartItem is like join table as well for product and cart (product <--> cart many to many)
class CartItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cart_id: Optional[int] = Field(sa_column=Column(ForeignKey("cart.id", ondelete="SET NULL"), nullable=True))
    product_id: int = Field(sa_column=Column(ForeignKey("product.id", ondelete="CASCADE"), nullable=False))
    quantity: int = Field(default=1)
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    deleted_at: Optional[datetime] = Field(default=None,sa_column=Column(DateTime(timezone=True)))


    cart: "Cart" = Relationship(back_populates="cart_items")

    # unique constraint for insertion safety at db level
    __table_args__ = (
        UniqueConstraint("cart_id", "product_id", name="uq_cart_product"),
    )