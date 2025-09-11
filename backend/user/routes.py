
import asyncio
import os
import uuid
from PIL import UnidentifiedImageError
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile , status
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.background_workers.thumbnail_task_handler import ThumbnailTaskHandler
from backend.db.dependencies import get_session
from backend.user.repository import save_user_avatar
from backend.user.utils import FileUpload, file_hash
from backend.config.media_config import media_settings
from backend.api.routers import user_router


FILE_SECRET_KEY=media_settings.FILE_SECRET_KEY

file_upload=FileUpload()


#* only admin can see other user's public details
# accessible only to same user 
@user_router.get("/me")
async def get_user_profile(request:Request, session: AsyncSession = Depends(get_session)):
    return {"message":request.state.user_identifier}

#*WARN DB Save plus (enqueued)extra image processing are not atomic safe .
@user_router.post("/me/upload-profile-img")
async def upload_profile_image(request:Request,file: UploadFile = File(), session = Depends(get_session)):
    
    user_identifier = request.state.user_identifier
    app=request.app

    #** add more robust checks
    # cheap header check
    if not file.content_type or file.content_type.split("/")[0] != "image":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image uploads allowed")
    
    user_specific_path=f"{file_hash(user_identifier.id,FILE_SECRET_KEY)}"
    dest_dir=file_upload._make_profile_path(user_specific_path)
    tmp_path = dest_dir / f"upload_{uuid.uuid4().hex}.tmp"  # unique temp 

    # prepare safe paths and temp file
    try:
        await asyncio.to_thread(file_upload._stream_save_to_disk_sync, file.file, tmp_path)
    except ValueError:
        # file too large
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File too large (max {file_upload.MAX_UPLOAD_SIZE} bytes)")
    except Exception as e:
        # cleanup
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save upload") from e
    finally:
        # close starlette UploadFile internals
        await file.close()

    # verify image
    try:
        fmt=await asyncio.to_thread(file_upload._verify_image_sync, tmp_path)
    except UnidentifiedImageError:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image")
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Image verification failed")

    
    final_name = f"profile_{user_specific_path}{fmt}"  # since one profile per user
    final_path = dest_dir / final_name

    # atomic rename
    try:
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to finalize upload")
    
    print("rel path")
    # store relative path in DB: 
    rel_path = f"{user_specific_path}/{final_name}"
    
    media_id:int=await save_user_avatar(session, user_identifier.id, rel_path,final_path)
    if not media_id or type(media_id) is not int:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save avatar")
    
    event="image_uploaded"
    data={"user_id": user_identifier.id, "media_id": media_id,"rel_path":rel_path}
    try:
        app.state.pubsub_pub(event,data)
        # logger.info("[upload] enqueued thumbnail task for user=%s row=%s", user_identifier.id, media_id)
    except asyncio.QueueFull as e:
        print("Failed to enqueue task", e)
        # logger.error("[upload] queue full ,cannot enqueue")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process upload")

    return {"message": "uploaded", "image_path": rel_path}




