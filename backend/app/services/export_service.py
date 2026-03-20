"""
Export service for generating MS Project and PDF exports.
"""
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT


class ExportService:
    """Service for exporting project data to various formats."""
    
    @staticmethod
    def export_to_ms_project(project_data: Dict, tasks: List[Dict], resources: List[Dict]) -> bytes:
        """
        Export project data to Microsoft Project XML format.
        Returns XML content as bytes.
        """
        # Create root XML structure for MS Project 2010+ format
        project = ET.Element("Project", xmlns="http://schemas.microsoft.com/project")
        
        # Add project properties
        name_elem = ET.SubElement(project, "Name")
        name_elem.text = project_data.get("name", "Untitled Project")
        
        title_elem = ET.SubElement(project, "Title")
        title_elem.text = project_data.get("name", "")
        
        start_date_elem = ET.SubElement(project, "StartDate")
        start_date_elem.text = project_data.get("start_date", datetime.now().isoformat())
        
        finish_date_elem = ET.SubElement(project, "FinishDate")
        finish_date_elem.text = project_data.get("end_date", datetime.now().isoformat())
        
        # Add tasks section
        tasks_elem = ET.SubElement(project, "Tasks")
        
        for idx, task in enumerate(tasks, start=1):
            task_elem = ET.SubElement(tasks_elem, "Task")
            
            uid = ET.SubElement(task_elem, "UID")
            uid.text = str(idx)
            
            task_id = ET.SubElement(task_elem, "ID")
            task_id.text = str(task.get("id", idx))
            
            task_name = ET.SubElement(task_elem, "Name")
            task_name.text = task.get("name", f"Task {idx}")
            
            task_start = ET.SubElement(task_elem, "Start")
            task_start.text = task.get("start_date", "")
            
            task_finish = ET.SubElement(task_elem, "Finish")
            task_finish.text = task.get("end_date", "")
            
            duration = ET.SubElement(task_elem, "Duration")
            duration.text = f"PT{task.get('duration', 0)}H"
            
            percent_complete = ET.SubElement(task_elem, "PercentComplete")
            percent_complete.text = str(task.get("progress", 0))
            
            priority = ET.SubElement(task_elem, "Priority")
            priority_map = {"low": "300", "medium": "500", "high": "700", "critical": "900"}
            priority.text = priority_map.get(task.get("priority", "medium"), "500")
            
            # Add predecessor links if dependencies exist
            if task.get("dependencies"):
                predecessor_link_elem = ET.SubElement(task_elem, "PredecessorLink")
                predecessor_uid = ET.SubElement(predecessor_link_elem, "PredecessorUID")
                predecessor_uid.text = str(task["dependencies"][0])  # Simplified
        
        # Add resources section
        resources_elem = ET.SubElement(project, "Resources")
        
        for idx, resource in enumerate(resources, start=1):
            resource_elem = ET.SubElement(resources_elem, "Resource")
            
            uid = ET.SubElement(resource_elem, "UID")
            uid.text = str(idx)
            
            res_id = ET.SubElement(resource_elem, "ID")
            res_id.text = str(resource.get("id", idx))
            
            res_name = ET.SubElement(resource_elem, "Name")
            res_name.text = resource.get("name", f"Resource {idx}")
            
            res_type = ET.SubElement(resource_elem, "Type")
            res_type.text = "1"  # 1 = Work resource
        
        # Convert to XML string
        tree = ET.ElementTree(project)
        xml_io = io.BytesIO()
        tree.write(xml_io, encoding='utf-8', xml_declaration=True)
        xml_io.seek(0)
        
        return xml_io.getvalue()
    
    @staticmethod
    def export_gantt_to_pdf(project_data: Dict, tasks: List[Dict], milestones: List[Dict]) -> bytes:
        """
        Export Gantt chart to PDF format.
        Returns PDF content as bytes.
        """
        buffer = io.BytesIO()
        
        # Create PDF document with landscape orientation
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.5*inch
        )
        
        # Container for PDF elements
        elements = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1976d2'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.grey,
            spaceAfter=20,
            alignment=TA_CENTER
        )
        
        # Title
        title = Paragraph(f"Gantt Chart: {project_data.get('name', 'Project')}", title_style)
        elements.append(title)
        
        # Subtitle with dates
        subtitle_text = f"Period: {project_data.get('start_date', 'N/A')} to {project_data.get('end_date', 'N/A')}"
        subtitle = Paragraph(subtitle_text, subtitle_style)
        elements.append(subtitle)
        
        # Tasks table
        if tasks:
            task_data = [['Task', 'Start Date', 'End Date', 'Duration', 'Progress', 'Status', 'Assignee']]
            
            for task in tasks:
                task_data.append([
                    task.get('name', 'N/A')[:30],  # Truncate long names
                    task.get('start_date', 'N/A')[:10] if task.get('start_date') else 'N/A',
                    task.get('end_date', 'N/A')[:10] if task.get('end_date') else 'N/A',
                    f"{task.get('duration', 0)}d",
                    f"{task.get('progress', 0)}%",
                    task.get('status', 'N/A'),
                    task.get('assignee_name', 'Unassigned')[:20]
                ])
            
            # Create table
            task_table = Table(task_data, colWidths=[2.5*inch, 1*inch, 1*inch, 0.8*inch, 0.8*inch, 1*inch, 1.5*inch])
            task_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976d2')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
            ]))
            
            elements.append(task_table)
            elements.append(Spacer(1, 0.3*inch))
        
        # Milestones section
        if milestones:
            milestone_title = Paragraph("Milestones", styles['Heading2'])
            elements.append(PageBreak())
            elements.append(milestone_title)
            elements.append(Spacer(1, 0.2*inch))
            
            milestone_data = [['Milestone', 'Due Date', 'Status', 'Description']]
            
            for milestone in milestones:
                milestone_data.append([
                    milestone.get('name', 'N/A')[:40],
                    milestone.get('due_date', 'N/A')[:10] if milestone.get('due_date') else 'N/A',
                    milestone.get('status', 'N/A'),
                    milestone.get('description', '')[:60]
                ])
            
            milestone_table = Table(milestone_data, colWidths=[2.5*inch, 1.2*inch, 1*inch, 4*inch])
            milestone_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#388e3c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            
            elements.append(milestone_table)
        
        # Build PDF
        doc.build(elements)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    @staticmethod
    def export_report_to_pdf(report_title: str, report_data: Dict, charts: List = None) -> bytes:
        """
        Export general report to PDF format.
        Returns PDF content as bytes.
        """
        buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=0.75*inch
        )
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1976d2'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        title = Paragraph(report_title, title_style)
        elements.append(title)
        
        # Timestamp
        timestamp = Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            styles['Normal']
        )
        elements.append(timestamp)
        elements.append(Spacer(1, 0.3*inch))
        
        # Report content
        for section_title, section_content in report_data.items():
            section_heading = Paragraph(section_title, styles['Heading2'])
            elements.append(section_heading)
            elements.append(Spacer(1, 0.1*inch))
            
            if isinstance(section_content, dict):
                # Key-value pairs
                for key, value in section_content.items():
                    text = f"<b>{key}:</b> {value}"
                    para = Paragraph(text, styles['Normal'])
                    elements.append(para)
            elif isinstance(section_content, list):
                # List items
                for item in section_content:
                    text = f"• {item}"
                    para = Paragraph(text, styles['Normal'])
                    elements.append(para)
            else:
                # Plain text
                para = Paragraph(str(section_content), styles['Normal'])
                elements.append(para)
            
            elements.append(Spacer(1, 0.2*inch))
        
        doc.build(elements)
        
        buffer.seek(0)
        return buffer.getvalue()
