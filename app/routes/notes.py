from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.note import Note
from app.models.resource import Resource
from app.schemas.note import NoteCreate, NoteUpdate, NoteResponse


router = APIRouter(
    prefix="/api/notes",
    tags=["Notes"]
)


# Create a note
@router.post("/", response_model=NoteResponse)
def create_note(
    note_data: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # If note is linked to a resource, verify ownership
    if note_data.resource_id is not None:
        resource = (
            db.query(Resource)
            .filter(
                Resource.id == note_data.resource_id,
                Resource.user_id == current_user.id
            )
            .first()
        )

        if resource is None:
            raise HTTPException(
                status_code=404,
                detail="Resource not found"
            )

    note = Note(
        user_id=current_user.id,
        resource_id=note_data.resource_id,
        title=note_data.title,
        content=note_data.content
    )

    db.add(note)
    db.commit()
    db.refresh(note)

    return note


# Get all notes
@router.get("/", response_model=list[NoteResponse])
def get_notes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notes = (
        db.query(Note)
        .filter(Note.user_id == current_user.id)
        .order_by(Note.created_at.desc())
        .all()
    )

    return notes


# Get one note
@router.get("/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    note = (
        db.query(Note)
        .filter(
            Note.id == note_id,
            Note.user_id == current_user.id
        )
        .first()
    )

    if note is None:
        raise HTTPException(
            status_code=404,
            detail="Note not found"
        )

    return note


# Update a note
@router.put("/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    note_data: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    note = (
        db.query(Note)
        .filter(
            Note.id == note_id,
            Note.user_id == current_user.id
        )
        .first()
    )

    if note is None:
        raise HTTPException(
            status_code=404,
            detail="Note not found"
        )

    # If changing/adding resource link, verify ownership
    if note_data.resource_id is not None:
        resource = (
            db.query(Resource)
            .filter(
                Resource.id == note_data.resource_id,
                Resource.user_id == current_user.id
            )
            .first()
        )

        if resource is None:
            raise HTTPException(
                status_code=404,
                detail="Resource not found"
            )

    if note_data.title is not None:
        note.title = note_data.title

    if note_data.content is not None:
        note.content = note_data.content

    if note_data.resource_id is not None:
        note.resource_id = note_data.resource_id

    db.commit()
    db.refresh(note)

    return note


# Delete a note
@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    note = (
        db.query(Note)
        .filter(
            Note.id == note_id,
            Note.user_id == current_user.id
        )
        .first()
    )

    if note is None:
        raise HTTPException(
            status_code=404,
            detail="Note not found"
        )

    db.delete(note)
    db.commit()

    return {
        "message": "Note deleted successfully"
    }