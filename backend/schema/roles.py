# from typing import Optional, List 
# from sqlmodel import SQLModel, Field, Relationship, Column 
# from sqlalchemy import String, UniqueConstraint

# # Join tables
# class UserRole(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True,nullable=False)
#     #* add user_phone id as well later 
#     role_id: Optional[int] = Field(default=None, foreign_key="role.id", index=True,nullable=False)

#     __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role_user_id_role_id"),)

# class RolePermission(SQLModel, table=True):
#     id:Optional[int] = Field(default=None, primary_key=True)
#     role_id: Optional[int] = Field(default=None, foreign_key="role.id", index=True,nullable=False)
#     permission_id: Optional[int] = Field(default=None, foreign_key="permission.id", index=True,nullable=False)

#     __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission_role_id_permission_id"),)

# # Core tables
# class Role(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     name: str = Field(sa_column=Column(String(length=200), unique=True, nullable=False,default='buyer'))
#     description: Optional[str] = None
#     user: List["Users"] = Relationship(back_populates="roles",link_model=UserRole)
#     permissions: List["Permission"] = Relationship(back_populates="roles", link_model=RolePermission)

# class Permission(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     name: str = Field(sa_column=Column(String, unique=True, nullable=False))
#     description: Optional[str] = None
#     roles: List["Role"] = Relationship(back_populates="permissions", link_model=RolePermission)
