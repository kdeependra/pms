from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.models.models import Project, Task, Milestone, Resource
from app.api.v1.endpoints.auth import get_current_user
from app.services.export_service import ExportService

router = APIRouter()


@router.get("/projects/{project_id}/export/ms-project")
async def export_project_to_ms_project(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export project to Microsoft Project XML format."""
    # Get project
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get tasks
    result = await db.execute(
        select(Task).where(Task.project_id == project_id)
    )
    tasks = result.scalars().all()
    
    # Get resources (from task assignments)
    result = await db.execute(
        select(Resource).distinct()
    )
    resources = result.scalars().all()
    
    # Prepare data
    project_data = {
        "name": project.name,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None
    }
    
    tasks_data = [
        {
            "id": task.id,
            "name": task.name,
            "start_date": task.start_date.isoformat() if task.start_date else "",
            "end_date": task.end_date.isoformat() if task.end_date else "",
            "duration": task.duration or 0,
            "progress": task.progress,
            "priority": task.priority,
            "dependencies": []  # Would need to query task_dependencies table
        }
        for task in tasks
    ]
    
    resources_data = [
        {
            "id": res.id,
            "name": res.name
        }
        for res in resources
    ]
    
    # Generate export
    xml_content = ExportService.export_to_ms_project(project_data, tasks_data, resources_data)
    
    # Return as downloadable file
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename={project.name.replace(' ', '_')}_export.xml"
        }
    )


@router.get("/projects/{project_id}/export/gantt-pdf")
async def export_gantt_to_pdf(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Export Gantt chart to PDF format."""
    # Get project
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get tasks with assignee names
    result = await db.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.start_date)
    )
    tasks = result.scalars().all()
    
    # Get milestones
    result = await db.execute(
        select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.due_date)
    )
    milestones = result.scalars().all()
    
    # Prepare data
    project_data = {
        "name": project.name,
        "start_date": project.start_date.strftime('%Y-%m-%d') if project.start_date else 'N/A',
        "end_date": project.end_date.strftime('%Y-%m-%d') if project.end_date else 'N/A'
    }
    
    tasks_data = [
        {
            "name": task.name,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "end_date": task.end_date.isoformat() if task.end_date else None,
            "duration": task.duration or 0,
            "progress": task.progress,
            "status": task.status,
            "assignee_name": "Assigned User"  # Would need to join with User table
        }
        for task in tasks
    ]
    
    milestones_data = [
        {
            "name": milestone.name,
            "due_date": milestone.due_date.isoformat() if milestone.due_date else None,
            "status": milestone.status,
            "description": milestone.description or ""
        }
        for milestone in milestones
    ]
    
    # Generate PDF
    pdf_content = ExportService.export_gantt_to_pdf(project_data, tasks_data, milestones_data)
    
    # Return as downloadable file
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={project.name.replace(' ', '_')}_gantt.pdf"
        }
    )


@router.post("/reports/export/pdf")
async def export_report_to_pdf(
    report_title: str,
    report_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Export a custom report to PDF format."""
    pdf_content = ExportService.export_report_to_pdf(report_title, report_data)
    
    # Return as downloadable file
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={report_title.replace(' ', '_')}_report.pdf"
        }
    )
