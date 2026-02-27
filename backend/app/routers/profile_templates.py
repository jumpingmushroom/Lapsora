"""Profile template management endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, ProfileTemplate, Stream
from app.schemas import (
    ApplyTemplateRequest,
    ProfileRead,
    ProfileTemplateCreate,
    ProfileTemplateRead,
    ProfileTemplateUpdate,
)
from app.services import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile-templates", tags=["profile-templates"])


@router.get("/", response_model=list[ProfileTemplateRead])
def list_templates(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ProfileTemplate)
    if category:
        q = q.filter(ProfileTemplate.category == category)
    return q.order_by(ProfileTemplate.category, ProfileTemplate.name).all()


@router.get("/{template_id}", response_model=ProfileTemplateRead)
def get_template(template_id: int, db: Session = Depends(get_db)):
    template = db.get(ProfileTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return template


@router.post("/", response_model=ProfileTemplateRead, status_code=201)
def create_template(body: ProfileTemplateCreate, db: Session = Depends(get_db)):
    template = ProfileTemplate(**body.model_dump(), is_system=False)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.put("/{template_id}", response_model=ProfileTemplateRead)
def update_template(
    template_id: int, body: ProfileTemplateUpdate, db: Session = Depends(get_db)
):
    template = db.get(ProfileTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    if template.is_system:
        raise HTTPException(403, "System templates cannot be modified")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    template = db.get(ProfileTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    if template.is_system:
        raise HTTPException(403, "System templates cannot be deleted")

    db.delete(template)
    db.commit()


@router.post("/{template_id}/apply", response_model=ProfileRead, status_code=201)
def apply_template(
    template_id: int, body: ApplyTemplateRequest, db: Session = Depends(get_db)
):
    template = db.get(ProfileTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    stream = db.get(Stream, body.stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    profile = Profile(
        stream_id=body.stream_id,
        name=body.name or template.name,
        interval_seconds=template.interval_seconds,
        resolution_width=template.resolution_width,
        resolution_height=template.resolution_height,
        quality=template.quality,
        hdr_enabled=template.hdr_enabled,
        source_template_id=template.id,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    if profile.enabled:
        scheduler.add_capture_job(profile)

    return profile
