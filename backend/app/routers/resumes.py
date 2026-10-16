from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.additional import Resume
from app.models.core import Student
from app.schemas import ResumeRead


router = APIRouter(
    prefix="/resumes",
    tags=["Resumes"],
)


@router.post("/upload", response_model=ResumeRead, status_code=201)
async def upload_resume(
    student_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found",
        )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="A file is required",
        )

    original_filename = Path(file.filename).name
    file_extension = Path(original_filename).suffix.lower()
    allowed_extensions = {".pdf", ".doc", ".docx"}

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, DOC, and DOCX files are allowed",
        )

    file_contents = await file.read()

    if len(file_contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="File must be smaller than 5 MB",
        )

    project_root = Path(__file__).resolve().parents[3]
    upload_directory = project_root / "backend" / "uploads"
    upload_directory.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4().hex}{file_extension}"
    saved_file = upload_directory / stored_filename
    saved_file.write_bytes(file_contents)

    resume = Resume(
        student_id=student_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        file_path=f"backend/uploads/{stored_filename}",
    )

    db.add(resume)
    db.commit()
    db.refresh(resume)

    return resume