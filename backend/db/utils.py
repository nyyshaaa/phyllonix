

def _normalize_db_url(url: str | None) -> str | None:
    # Neon often returns "postgres://..." — asyncpg/SQLAlchemy needs "postgresql+asyncpg://..."
    if not url:
        return None
    if url.startswith("postgres://",):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url