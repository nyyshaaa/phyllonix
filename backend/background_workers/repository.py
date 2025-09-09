

from sqlalchemy import text


CLAIM_BATCH_SQL = text("""
WITH cte AS (
  SELECT id
  FROM usermedia
  WHERE profile_image_url IS NOT NULL AND (profile_image_thumb_url IS NULL)
  FOR UPDATE SKIP LOCKED
  LIMIT :limit
)
UPDATE usermedia
SET profile_image_thumb_url = :marker
FROM cte
WHERE usermedia.id = cte.id
RETURNING usermedia.id, usermedia.profile_image_url
""")
UPDATE_ROW_SQL = text("UPDATE usermedia SET profile_image_thumb_url = :thumb_path WHERE id = :id AND user_id =:user_id")
MARK_FAILED_SQL = text("UPDATE usermedia SET profile_image_thumb_url = NULL WHERE id = :id AND user_id =:user_id")
SELECT_MEDIA_ID=text("SELECT usermedia.id FROM usermedia WHERE id=:id")