
import asyncio
import os
import uuid
from PIL import UnidentifiedImageError
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile , status
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.repository import revoke_all_tokens_per_user
from backend.auth.utils import hash_password, validate_password, verify_password
from backend.background_workers.thumbnail_task_handler import ThumbnailTaskHandler
from backend.common.utils import success_response
from backend.db.dependencies import get_session
from backend.products.dependency import require_permissions
from backend.user.models import ChangePasswordIn, PromoteIn
from backend.user.repository import get_password_credential, get_rolenames_by_ids, save_user_avatar, update_password, userid_by_public_id, change_user_roles
from backend.user.utils import FileUpload, file_hash
from backend.config.media_config import media_settings
from typing import List
from sqlalchemy import delete
from backend.schema.full_schema import Role, UserRole, RoleAudit
from sqlalchemy import select, update


user_router=APIRouter()
user_admin_router=APIRouter()


FILE_SECRET_KEY=media_settings.FILE_SECRET_KEY

file_upload=FileUpload()


@user_router.get("/me")
async def get_user_profile(request:Request, session: AsyncSession = Depends(get_session)):
    return {"message":request.state.user_identifier}


@user_router.post(path="/me/password")
async def change_password(request:Request, payload: ChangePasswordIn, session: AsyncSession = Depends(get_session)):

    user_identifier = request.state.user_identifier

    is_valid, detail = validate_password(payload.new_password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    curr_pwd_hash = await get_password_credential(session, user_identifier)
    if not verify_password(payload.current_password, curr_pwd_hash):
        raise HTTPException(403, "Current password is incorrect")
    
    new_hash = hash_password(payload.new_password)
    updated_cred_id = await update_password(session, user_identifier, new_hash)
    if not updated_cred_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update password retry")
    
    # may also add device check as well by passing device public id for more security
    await revoke_all_tokens_per_user(session,user_identifier,revoked_by="password_change")

    await session.commit()

    return success_response({"message": "Password changed successfully"}, 200)


#*WARN DB Save plus (enqueued)extra image processing are not atomic safe .
@user_router.post("/me/upload-profile-img")
async def upload_profile_image(request:Request,file: UploadFile = File(), session = Depends(get_session)):
    
    user_identifier = request.state.user_identifier
    app=request.app

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


@user_admin_router.patch("/{user_public_id}/roles", dependencies=[require_permissions("user:manage")])
async def change_user_role(
    user_public_id: str,
    request: Request,
    payload: PromoteIn,
    session: AsyncSession = Depends(get_session)
):
   
    actor_user_id = request.state.user_identifier
    cur_roles = request.state.user_roles  # verified by authorization middleware

    target_user_id = await userid_by_public_id(session, user_public_id)
    if not target_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    role_names = await get_rolenames_by_ids(session,cur_roles)
   
    if actor_user_id == target_user_id and "admin" in role_names and "admin" not in payload.role_names:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="An admin cannot downgrade their role")

    role_version = await change_user_roles(
        session=session,
        user_id=target_user_id,
        cur_role_ids=cur_roles,
        new_role_names=payload.role_names,
        actor_user_id=actor_user_id,
        reason=payload.reason
    )
    await session.commit()
    
    
    return success_response({
        "message": f"User roles updated successfully ,role_version: {role_version}"}, 200)





