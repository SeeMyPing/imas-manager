"""
IMAS Manager - Notification Templates

Rich notification templates with Jinja2 support for dynamic content.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.template import Context, Template
from django.utils import timezone

if TYPE_CHECKING:
    from core.models import Incident, Runbook, Service, Team

logger = logging.getLogger(__name__)


# =============================================================================
# Template Context Builder
# =============================================================================


@dataclass
class NotificationContext:
    """
    Context data for rendering notification templates.
    """
    incident: "Incident"
    runbook: "Runbook | None" = None
    custom_data: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for template rendering."""
        data = {
            # Incident fields
            "incident_id": str(self.incident.id),
            "incident_short_id": self.incident.short_id,
            "incident_title": self.incident.title,
            "incident_description": self.incident.description,
            "incident_severity": self.incident.severity,
            "incident_severity_display": self.incident.get_severity_display(),
            "incident_status": self.incident.status,
            "incident_status_display": self.incident.get_status_display(),
            "incident_url": self._get_incident_url(),
            "incident_created_at": self.incident.created_at,
            "incident_created_at_iso": self.incident.created_at.isoformat() if self.incident.created_at else None,
            
            # Service fields
            "service_name": self.incident.service.name if self.incident.service else "Unknown",
            "service_criticality": self.incident.service.criticality if self.incident.service else None,
            "team_name": self.incident.service.owner_team.name if self.incident.service else "Unknown",
            
            # Lead fields
            "lead_name": self.incident.lead.get_full_name() if self.incident.lead else None,
            "lead_username": self.incident.lead.username if self.incident.lead else None,
            
            # Automation links
            "lid_link": self.incident.lid_link or None,
            "war_room_link": self.incident.war_room_link or None,
            
            # KPIs
            "mtta_seconds": self.incident.mtta_seconds,
            "mttr_seconds": self.incident.mttr_seconds,
            
            # Computed
            "is_critical": self.incident.is_critical,
            "is_open": self.incident.is_open,
            "timestamp": timezone.now().isoformat(),
        }
        
        # Add runbook data if available
        if self.runbook:
            data["runbook"] = {
                "name": self.runbook.name,
                "steps_count": self.runbook.steps.count(),
                "quick_actions": self.runbook.quick_actions,
                "external_docs": self.runbook.external_docs,
            }
        
        # Merge custom data
        data.update(self.custom_data)
        
        return data
    
    def _get_incident_url(self) -> str:
        """Get the URL to the incident dashboard."""
        from django.conf import settings
        base_url = getattr(settings, "SITE_URL", "http://localhost:8000")
        return f"{base_url}/incidents/{self.incident.id}/"


# =============================================================================
# Slack Templates
# =============================================================================


class SlackTemplates:
    """
    Rich Slack message templates using Block Kit.
    """
    
    SEVERITY_COLORS = {
        "SEV1": "#DC2626",  # Red
        "SEV2": "#F97316",  # Orange
        "SEV3": "#EAB308",  # Yellow
        "SEV4": "#6B7280",  # Gray
    }
    
    SEVERITY_EMOJI = {
        "SEV1": "🔴",
        "SEV2": "🟠",
        "SEV3": "🟡",
        "SEV4": "⚪",
    }
    
    @classmethod
    def incident_created(cls, ctx: NotificationContext) -> dict:
        """
        Template for new incident notification.
        """
        data = ctx.to_dict()
        severity = data["incident_severity"]
        emoji = cls.SEVERITY_EMOJI.get(severity, "⚪")
        color = cls.SEVERITY_COLORS.get(severity, "#6B7280")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} New Incident: {data['incident_short_id']}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{data['incident_title']}*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{data['incident_severity_display']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Service:*\n{data['service_name']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Team:*\n{data['team_name']}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{data['incident_status_display']}",
                    },
                ],
            },
        ]
        
        # Add description if present
        if data["incident_description"]:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{data['incident_description'][:500]}```",
                },
            })
        
        # Add action buttons
        actions = []
        
        actions.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "🔍 View Incident"},
            "url": data["incident_url"],
            "action_id": "view_incident",
        })
        
        if data.get("war_room_link"):
            actions.append({
                "type": "button",
                "text": {"type": "plain_text", "text": "💬 War Room"},
                "url": data["war_room_link"],
                "action_id": "join_war_room",
                "style": "primary",
            })
        
        if data.get("lid_link"):
            actions.append({
                "type": "button",
                "text": {"type": "plain_text", "text": "📄 LID Doc"},
                "url": data["lid_link"],
                "action_id": "view_lid",
            })
        
        # Add runbook button if available
        if data.get("runbook"):
            actions.append({
                "type": "button",
                "text": {"type": "plain_text", "text": "📚 Runbook"},
                "action_id": "show_runbook",
                "style": "primary",
            })
        
        blocks.append({
            "type": "actions",
            "elements": actions[:5],  # Slack limits to 5 actions
        })
        
        # Add context footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Created at {data['incident_created_at'].strftime('%Y-%m-%d %H:%M UTC') if data['incident_created_at'] else 'N/A'} • ID: {data['incident_id']}",
                },
            ],
        })
        
        return {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                }
            ],
        }
    
    @classmethod
    def incident_acknowledged(cls, ctx: NotificationContext) -> dict:
        """Template for incident acknowledgement."""
        data = ctx.to_dict()
        
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *Incident Acknowledged*: {data['incident_short_id']}\n"
                                f"_{data['incident_title']}_",
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Acknowledged by *{data.get('acknowledged_by', 'Unknown')}* • "
                                    f"MTTA: {cls._format_duration(data['mtta_seconds'])}",
                        },
                    ],
                },
            ],
        }
    
    @classmethod
    def incident_resolved(cls, ctx: NotificationContext) -> dict:
        """Template for incident resolution."""
        data = ctx.to_dict()
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🎉 Incident Resolved",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{data['incident_short_id']}*: {data['incident_title']}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*MTTR:*\n{cls._format_duration(data['mttr_seconds'])}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Service:*\n{data['service_name']}",
                    },
                ],
            },
        ]
        
        # Add resolution note if provided
        resolution_note = data.get("resolution_note")
        if resolution_note:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Resolution:*\n{resolution_note}",
                },
            })
        
        return {"blocks": blocks}
    
    @classmethod
    def escalation_notification(cls, ctx: NotificationContext, escalation_level: int) -> dict:
        """Template for escalation notifications."""
        data = ctx.to_dict()
        severity = data["incident_severity"]
        emoji = cls.SEVERITY_EMOJI.get(severity, "⚪")
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"⚡ Escalation Level {escalation_level}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{data['incident_short_id']}*: {data['incident_title']}\n\n"
                                f"_This incident has not been acknowledged and is being escalated._",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Severity:*\n{data['incident_severity_display']}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Waiting:*\n{cls._format_duration(data.get('wait_time_seconds', 0))}",
                        },
                    ],
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "🔔 Acknowledge Now"},
                            "style": "danger",
                            "action_id": "acknowledge_incident",
                            "value": str(data["incident_id"]),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "🔍 View Details"},
                            "url": data["incident_url"],
                            "action_id": "view_incident",
                        },
                    ],
                },
            ],
        }
    
    @classmethod
    def runbook_notification(cls, runbook: "Runbook") -> dict:
        """Template for runbook suggestion."""
        steps = list(runbook.steps.all()[:5])
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📚 Runbook: {runbook.name}",
                    "emoji": True,
                },
            },
        ]
        
        if runbook.description:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": runbook.description,
                },
            })
        
        # Add quick actions
        if runbook.quick_actions:
            actions = []
            for action in runbook.quick_actions[:4]:
                actions.append({
                    "type": "button",
                    "text": {"type": "plain_text", "text": action.get("label", "Action")[:20]},
                    "action_id": f"runbook_action_{action.get('id', 'unknown')}",
                })
            if actions:
                blocks.append({
                    "type": "actions",
                    "elements": actions,
                })
        
        # Add steps preview
        if steps:
            steps_text = "\n".join([
                f"{i+1}. {step.title}" for i, step in enumerate(steps)
            ])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Steps:*\n{steps_text}",
                },
            })
        
        return {"blocks": blocks}
    
    @staticmethod
    def _format_duration(seconds: int | None) -> str:
        """Format duration in human-readable format."""
        if seconds is None:
            return "N/A"
        
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"


# =============================================================================
# Email Templates
# =============================================================================


class EmailTemplates:
    """
    HTML email templates for notifications.
    """
    
    @classmethod
    def incident_created(cls, ctx: NotificationContext) -> tuple[str, str]:
        """
        Generate email for new incident.
        
        Returns: (subject, html_body)
        """
        data = ctx.to_dict()
        
        subject = f"[{data['incident_severity']}] {data['incident_short_id']}: {data['incident_title']}"
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #DC2626; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; }}
        .field {{ margin-bottom: 15px; }}
        .label {{ font-weight: 600; color: #374151; }}
        .value {{ color: #6b7280; }}
        .button {{ display: inline-block; padding: 12px 24px; background: #2563eb; color: white; 
                   text-decoration: none; border-radius: 6px; margin-right: 10px; }}
        .button-secondary {{ background: #6b7280; }}
        .footer {{ padding: 15px; text-align: center; color: #9ca3af; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">🔴 New Incident</h1>
            <p style="margin: 5px 0 0 0;">{data['incident_short_id']}</p>
        </div>
        <div class="content">
            <h2>{data['incident_title']}</h2>
            
            <div class="field">
                <span class="label">Severity:</span>
                <span class="value">{data['incident_severity_display']}</span>
            </div>
            
            <div class="field">
                <span class="label">Service:</span>
                <span class="value">{data['service_name']}</span>
            </div>
            
            <div class="field">
                <span class="label">Team:</span>
                <span class="value">{data['team_name']}</span>
            </div>
            
            <div class="field">
                <span class="label">Description:</span>
                <p class="value">{data['incident_description'] or 'No description provided.'}</p>
            </div>
            
            <div style="margin-top: 20px;">
                <a href="{data['incident_url']}" class="button">View Incident</a>
                {'<a href="' + data['war_room_link'] + '" class="button button-secondary">Join War Room</a>' if data.get('war_room_link') else ''}
            </div>
        </div>
        <div class="footer">
            IMAS Manager • Incident Management At Scale
        </div>
    </div>
</body>
</html>
"""
        
        return subject, html_body
    
    @classmethod
    def escalation_notification(cls, ctx: NotificationContext, escalation_level: int) -> tuple[str, str]:
        """
        Generate email for escalation.
        
        Returns: (subject, html_body)
        """
        data = ctx.to_dict()
        
        subject = f"⚡ ESCALATION #{escalation_level} - [{data['incident_severity']}] {data['incident_short_id']}"
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #F97316; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #fff7ed; padding: 20px; border: 1px solid #fed7aa; }}
        .button {{ display: inline-block; padding: 12px 24px; background: #dc2626; color: white; 
                   text-decoration: none; border-radius: 6px; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0;">⚡ Escalation Level {escalation_level}</h1>
            <p style="margin: 5px 0 0 0;">Immediate attention required</p>
        </div>
        <div class="content">
            <h2>{data['incident_short_id']}: {data['incident_title']}</h2>
            
            <p><strong>This incident has not been acknowledged and is being escalated to you.</strong></p>
            
            <p>
                <strong>Severity:</strong> {data['incident_severity_display']}<br>
                <strong>Service:</strong> {data['service_name']}<br>
                <strong>Waiting since:</strong> {data.get('wait_time_seconds', 0) // 60} minutes
            </p>
            
            <div style="margin-top: 20px; text-align: center;">
                <a href="{data['incident_url']}" class="button">🔔 Acknowledge Now</a>
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        return subject, html_body


# =============================================================================
# Template Registry
# =============================================================================


class TemplateRegistry:
    """
    Registry for notification templates.
    """
    
    TEMPLATES = {
        "slack": SlackTemplates,
        "email": EmailTemplates,
    }
    
    @classmethod
    def get_template(cls, channel: str, template_name: str, ctx: NotificationContext, **kwargs) -> Any:
        """
        Get a rendered template.
        
        Args:
            channel: Notification channel (slack, email, etc.)
            template_name: Name of the template (incident_created, etc.)
            ctx: Notification context
            **kwargs: Additional arguments for the template
        
        Returns:
            Rendered template (format depends on channel)
        """
        template_class = cls.TEMPLATES.get(channel)
        if not template_class:
            raise ValueError(f"Unknown channel: {channel}")
        
        template_method = getattr(template_class, template_name, None)
        if not template_method:
            raise ValueError(f"Unknown template: {template_name} for channel {channel}")
        
        return template_method(ctx, **kwargs)
