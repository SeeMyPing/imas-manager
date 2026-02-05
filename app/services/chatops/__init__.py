"""
IMAS Manager - ChatOps Service

Handles Slack slash commands and interactive components
for incident management directly from Slack.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from core.models import Incident, User

logger = logging.getLogger(__name__)


class SlackCommandType(str, Enum):
    """Supported slash command actions."""
    
    CREATE = "create"
    ACK = "ack"
    ACKNOWLEDGE = "acknowledge"
    RESOLVE = "resolve"
    ESCALATE = "escalate"
    LIST = "list"
    STATUS = "status"
    HELP = "help"


@dataclass
class SlackCommand:
    """Parsed Slack slash command."""
    
    action: SlackCommandType
    args: list[str]
    incident_id: str | None = None
    raw_text: str = ""


@dataclass
class SlackCommandResult:
    """Result of a slash command execution."""
    
    success: bool
    response_type: str = "ephemeral"  # "ephemeral" or "in_channel"
    text: str = ""
    blocks: list[dict] | None = None
    attachments: list[dict] | None = None


class SlackSignatureVerifier:
    """
    Verify Slack request signatures for security.
    
    Slack signs all requests with a shared secret to verify authenticity.
    """
    
    def __init__(self, signing_secret: str):
        self.signing_secret = signing_secret
    
    def verify(
        self,
        signature: str,
        timestamp: str,
        body: bytes,
    ) -> bool:
        """
        Verify a Slack request signature.
        
        Args:
            signature: X-Slack-Signature header value.
            timestamp: X-Slack-Request-Timestamp header value.
            body: Raw request body bytes.
            
        Returns:
            True if signature is valid.
        """
        # Check timestamp is recent (within 5 minutes)
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            if abs(current_time - request_time) > 300:
                logger.warning("Slack request timestamp too old")
                return False
        except (ValueError, TypeError):
            return False
        
        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_sig = (
            "v0="
            + hmac.new(
                self.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )
        
        # Constant-time comparison
        return hmac.compare_digest(expected_sig, signature)


class ChatOpsService:
    """
    Service for handling ChatOps commands from Slack.
    
    Supports:
    - /incident create <title> - Create new incident
    - /incident ack <id> - Acknowledge incident
    - /incident resolve <id> [message] - Resolve incident
    - /incident escalate <id> - Escalate incident
    - /incident list - List open incidents
    - /incident status <id> - Get incident status
    - /incident help - Show help
    """
    
    def __init__(self):
        self.signing_secret = getattr(settings, "SLACK_SIGNING_SECRET", "")
        self.verifier = SlackSignatureVerifier(self.signing_secret)
    
    def verify_request(
        self,
        signature: str,
        timestamp: str,
        body: bytes,
    ) -> bool:
        """Verify Slack request signature."""
        if not self.signing_secret:
            logger.warning("SLACK_SIGNING_SECRET not configured")
            return False
        return self.verifier.verify(signature, timestamp, body)
    
    def parse_command(self, text: str) -> SlackCommand:
        """
        Parse slash command text into structured command.
        
        Args:
            text: Raw command text (e.g., "ack INC-123" or "create High latency on API")
            
        Returns:
            Parsed SlackCommand.
        """
        text = text.strip()
        parts = text.split(maxsplit=1)
        
        if not parts:
            return SlackCommand(
                action=SlackCommandType.HELP,
                args=[],
                raw_text=text,
            )
        
        action_str = parts[0].lower()
        remaining = parts[1] if len(parts) > 1 else ""
        
        # Map to action type
        try:
            action = SlackCommandType(action_str)
        except ValueError:
            # Unknown action, default to help
            return SlackCommand(
                action=SlackCommandType.HELP,
                args=[text],
                raw_text=text,
            )
        
        # Extract incident ID if present
        incident_id = None
        args = []
        
        if action in (
            SlackCommandType.ACK,
            SlackCommandType.ACKNOWLEDGE,
            SlackCommandType.RESOLVE,
            SlackCommandType.ESCALATE,
            SlackCommandType.STATUS,
        ):
            # First arg should be incident ID
            arg_parts = remaining.split(maxsplit=1)
            if arg_parts:
                incident_id = self._extract_incident_id(arg_parts[0])
                args = arg_parts[1:] if len(arg_parts) > 1 else []
        elif action == SlackCommandType.CREATE:
            args = [remaining] if remaining else []
        elif action == SlackCommandType.LIST:
            args = remaining.split() if remaining else []
        
        return SlackCommand(
            action=action,
            args=args,
            incident_id=incident_id,
            raw_text=text,
        )
    
    def _extract_incident_id(self, text: str) -> str | None:
        """
        Extract incident ID from text.
        
        Handles formats: INC-123, inc-123, 123, <UUID>
        """
        text = text.strip().upper()
        
        # Format: INC-123
        if match := re.match(r"INC-?(\d+)", text):
            return match.group(1)
        
        # Format: Just number
        if text.isdigit():
            return text
        
        # Format: UUID
        uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        if re.match(uuid_pattern, text.lower()):
            return text.lower()
        
        return text if text else None
    
    async def execute_command(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None = None,
        channel_id: str | None = None,
    ) -> SlackCommandResult:
        """
        Execute a parsed Slack command.
        
        Args:
            command: Parsed SlackCommand.
            user_id: Slack user ID.
            user_email: User's email (for user lookup).
            channel_id: Slack channel ID.
            
        Returns:
            SlackCommandResult with response.
        """
        handlers = {
            SlackCommandType.CREATE: self._handle_create,
            SlackCommandType.ACK: self._handle_ack,
            SlackCommandType.ACKNOWLEDGE: self._handle_ack,
            SlackCommandType.RESOLVE: self._handle_resolve,
            SlackCommandType.ESCALATE: self._handle_escalate,
            SlackCommandType.LIST: self._handle_list,
            SlackCommandType.STATUS: self._handle_status,
            SlackCommandType.HELP: self._handle_help,
        }
        
        handler = handlers.get(command.action, self._handle_help)
        
        try:
            return await handler(command, user_id, user_email, channel_id)
        except Exception as e:
            logger.exception(f"Error executing ChatOps command: {e}")
            return SlackCommandResult(
                success=False,
                text=f"❌ Une erreur est survenue: {str(e)}",
            )
    
    # Sync version for non-async contexts
    def execute_command_sync(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None = None,
        channel_id: str | None = None,
    ) -> SlackCommandResult:
        """Synchronous version of execute_command."""
        import asyncio
        
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.execute_command(command, user_id, user_email, channel_id)
            )
        finally:
            loop.close()
    
    # -------------------------------------------------------------------------
    # Command Handlers
    # -------------------------------------------------------------------------
    
    async def _handle_create(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None,
        channel_id: str | None,
    ) -> SlackCommandResult:
        """Handle /incident create <title>."""
        from core.models import Incident, Service
        from core.models.incident import IncidentSeverity, IncidentStatus
        
        if not command.args:
            return SlackCommandResult(
                success=False,
                text="❌ Usage: `/incident create <titre de l'incident>`",
            )
        
        title = command.args[0]
        
        # Get or create user
        user = await self._get_or_create_user(user_email, user_id)
        
        # Create incident
        try:
            # Get default service if any
            default_service = await Service.objects.afirst()
            
            incident = await Incident.objects.acreate(
                title=title,
                description=f"Créé depuis Slack par <@{user_id}>",
                severity=IncidentSeverity.MEDIUM,
                status=IncidentStatus.OPEN,
                service=default_service,
                created_by=user,
            )
            
            incident_url = self._get_incident_url(incident)
            
            return SlackCommandResult(
                success=True,
                response_type="in_channel",
                text=f"✅ Incident créé: *{title}*",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🆕 *Nouvel incident créé*\n*ID:* `{incident.id}`\n*Titre:* {title}",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "🔍 Voir", "emoji": True},
                                "style": "primary",
                                "url": incident_url,
                                "action_id": "view_incident",
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "✅ Acquitter", "emoji": True},
                                "style": "primary",
                                "value": str(incident.id),
                                "action_id": "ack_incident",
                            },
                        ],
                    },
                ],
            )
        except Exception as e:
            logger.error(f"Failed to create incident: {e}")
            return SlackCommandResult(
                success=False,
                text=f"❌ Impossible de créer l'incident: {str(e)}",
            )
    
    async def _handle_ack(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None,
        channel_id: str | None,
    ) -> SlackCommandResult:
        """Handle /incident ack <id>."""
        from core.models import Incident
        from core.models.incident import IncidentStatus
        
        if not command.incident_id:
            return SlackCommandResult(
                success=False,
                text="❌ Usage: `/incident ack <ID>`\nExemple: `/incident ack INC-123`",
            )
        
        incident = await self._find_incident(command.incident_id)
        if not incident:
            return SlackCommandResult(
                success=False,
                text=f"❌ Incident `{command.incident_id}` non trouvé.",
            )
        
        if incident.status == IncidentStatus.RESOLVED:
            return SlackCommandResult(
                success=False,
                text=f"⚠️ L'incident `{command.incident_id}` est déjà résolu.",
            )
        
        if incident.status == IncidentStatus.ACKNOWLEDGED:
            return SlackCommandResult(
                success=False,
                text=f"⚠️ L'incident est déjà acquitté.",
            )
        
        # Acknowledge the incident
        incident.status = IncidentStatus.ACKNOWLEDGED
        incident.acknowledged_at = timezone.now()
        await incident.asave()
        
        return SlackCommandResult(
            success=True,
            response_type="in_channel",
            text=f"✅ Incident `{command.incident_id}` acquitté par <@{user_id}>",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *Incident acquitté*\n*ID:* `{incident.id}`\n*Titre:* {incident.title}\n*Par:* <@{user_id}>",
                    },
                },
            ],
        )
    
    async def _handle_resolve(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None,
        channel_id: str | None,
    ) -> SlackCommandResult:
        """Handle /incident resolve <id> [resolution message]."""
        from core.models import Incident
        from core.models.incident import IncidentStatus
        
        if not command.incident_id:
            return SlackCommandResult(
                success=False,
                text="❌ Usage: `/incident resolve <ID> [message]`\nExemple: `/incident resolve INC-123 Correction déployée`",
            )
        
        incident = await self._find_incident(command.incident_id)
        if not incident:
            return SlackCommandResult(
                success=False,
                text=f"❌ Incident `{command.incident_id}` non trouvé.",
            )
        
        if incident.status == IncidentStatus.RESOLVED:
            return SlackCommandResult(
                success=False,
                text=f"⚠️ L'incident `{command.incident_id}` est déjà résolu.",
            )
        
        # Resolve the incident
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = timezone.now()
        
        # Auto-acknowledge if not already
        if not incident.acknowledged_at:
            incident.acknowledged_at = timezone.now()
        
        await incident.asave()
        
        # Calculate resolution time
        resolution_time = incident.resolved_at - incident.created_at
        resolution_minutes = int(resolution_time.total_seconds() / 60)
        
        return SlackCommandResult(
            success=True,
            response_type="in_channel",
            text=f"🎉 Incident `{command.incident_id}` résolu par <@{user_id}>",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"🎉 *Incident résolu*\n"
                            f"*ID:* `{incident.id}`\n"
                            f"*Titre:* {incident.title}\n"
                            f"*Par:* <@{user_id}>\n"
                            f"*Temps de résolution:* {resolution_minutes} minutes"
                        ),
                    },
                },
            ],
        )
    
    async def _handle_escalate(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None,
        channel_id: str | None,
    ) -> SlackCommandResult:
        """Handle /incident escalate <id>."""
        from core.models import Incident
        from core.models.incident import IncidentSeverity
        
        if not command.incident_id:
            return SlackCommandResult(
                success=False,
                text="❌ Usage: `/incident escalate <ID>`",
            )
        
        incident = await self._find_incident(command.incident_id)
        if not incident:
            return SlackCommandResult(
                success=False,
                text=f"❌ Incident `{command.incident_id}` non trouvé.",
            )
        
        # Escalate severity
        severity_order = [
            IncidentSeverity.LOW,
            IncidentSeverity.MEDIUM,
            IncidentSeverity.HIGH,
            IncidentSeverity.CRITICAL,
        ]
        
        current_idx = severity_order.index(incident.severity)
        if current_idx >= len(severity_order) - 1:
            return SlackCommandResult(
                success=False,
                text=f"⚠️ L'incident est déjà au niveau de sévérité maximum (CRITICAL).",
            )
        
        old_severity = incident.severity
        incident.severity = severity_order[current_idx + 1]
        await incident.asave()
        
        return SlackCommandResult(
            success=True,
            response_type="in_channel",
            text=f"⬆️ Incident escaladé par <@{user_id}>",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"⬆️ *Incident escaladé*\n"
                            f"*ID:* `{incident.id}`\n"
                            f"*Titre:* {incident.title}\n"
                            f"*Sévérité:* {old_severity} → *{incident.severity}*\n"
                            f"*Par:* <@{user_id}>"
                        ),
                    },
                },
            ],
        )
    
    async def _handle_list(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None,
        channel_id: str | None,
    ) -> SlackCommandResult:
        """Handle /incident list [open|all]."""
        from core.models import Incident
        from core.models.incident import IncidentStatus
        
        show_all = "all" in command.args
        
        if show_all:
            incidents = Incident.objects.order_by("-created_at")[:10]
        else:
            incidents = Incident.objects.exclude(
                status=IncidentStatus.RESOLVED
            ).order_by("-created_at")[:10]
        
        incidents_list = [inc async for inc in incidents]
        
        if not incidents_list:
            return SlackCommandResult(
                success=True,
                text="✅ Aucun incident ouvert ! 🎉",
            )
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📋 Incidents {'(tous)' if show_all else 'ouverts'}",
                    "emoji": True,
                },
            },
        ]
        
        for incident in incidents_list:
            severity_emoji = self._get_severity_emoji(incident.severity)
            status_emoji = self._get_status_emoji(incident.status)
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{severity_emoji} *{incident.title}*\n"
                        f"`{str(incident.id)[:8]}...` | {status_emoji} {incident.status} | "
                        f"Créé {self._format_relative_time(incident.created_at)}"
                    ),
                },
            })
        
        return SlackCommandResult(
            success=True,
            blocks=blocks,
        )
    
    async def _handle_status(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None,
        channel_id: str | None,
    ) -> SlackCommandResult:
        """Handle /incident status <id>."""
        if not command.incident_id:
            return SlackCommandResult(
                success=False,
                text="❌ Usage: `/incident status <ID>`",
            )
        
        incident = await self._find_incident(command.incident_id)
        if not incident:
            return SlackCommandResult(
                success=False,
                text=f"❌ Incident `{command.incident_id}` non trouvé.",
            )
        
        severity_emoji = self._get_severity_emoji(incident.severity)
        status_emoji = self._get_status_emoji(incident.status)
        
        # Build status info
        fields = [
            f"*ID:* `{incident.id}`",
            f"*Titre:* {incident.title}",
            f"*Sévérité:* {severity_emoji} {incident.severity}",
            f"*Statut:* {status_emoji} {incident.status}",
            f"*Service:* {incident.service.name if incident.service else 'N/A'}",
            f"*Créé:* {self._format_relative_time(incident.created_at)}",
        ]
        
        if incident.acknowledged_at:
            fields.append(f"*Acquitté:* {self._format_relative_time(incident.acknowledged_at)}")
        
        if incident.resolved_at:
            fields.append(f"*Résolu:* {self._format_relative_time(incident.resolved_at)}")
        
        return SlackCommandResult(
            success=True,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(fields),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "🔍 Voir détails", "emoji": True},
                            "url": self._get_incident_url(incident),
                            "action_id": "view_incident",
                        },
                    ],
                },
            ],
        )
    
    async def _handle_help(
        self,
        command: SlackCommand,
        user_id: str,
        user_email: str | None,
        channel_id: str | None,
    ) -> SlackCommandResult:
        """Handle /incident help."""
        help_text = """
*📚 Commandes disponibles:*

• `/incident create <titre>` - Créer un nouvel incident
• `/incident ack <ID>` - Acquitter un incident
• `/incident resolve <ID> [message]` - Résoudre un incident
• `/incident escalate <ID>` - Escalader la sévérité
• `/incident list [all]` - Lister les incidents ouverts
• `/incident status <ID>` - Voir le statut d'un incident
• `/incident help` - Afficher cette aide

*Exemples:*
```
/incident create API Gateway timeout
/incident ack INC-123
/incident resolve INC-123 Hotfix déployé
/incident list
```
        """
        
        return SlackCommandResult(
            success=True,
            text=help_text,
        )
    
    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------
    
    async def _find_incident(self, incident_id: str) -> "Incident | None":
        """Find incident by ID (UUID or short ID)."""
        from core.models import Incident
        
        try:
            # Try UUID first
            return await Incident.objects.select_related(
                "service", "lead"
            ).aget(id=incident_id)
        except (Incident.DoesNotExist, ValueError):
            pass
        
        # Try searching by ID prefix
        try:
            return await Incident.objects.select_related(
                "service", "lead"
            ).filter(id__startswith=incident_id).afirst()
        except Exception:
            return None
    
    async def _get_or_create_user(
        self,
        email: str | None,
        slack_user_id: str,
    ) -> "User | None":
        """Get or create user from Slack info."""
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        if email:
            user, _ = await User.objects.aget_or_create(
                email=email,
                defaults={
                    "username": email.split("@")[0],
                    "slack_user_id": slack_user_id,
                },
            )
            return user
        
        # Try to find by Slack ID
        try:
            return await User.objects.aget(slack_user_id=slack_user_id)
        except User.DoesNotExist:
            return None
    
    def _get_incident_url(self, incident: "Incident") -> str:
        """Get URL for incident details page."""
        base_url = getattr(settings, "SITE_URL", "http://localhost:8000")
        return f"{base_url}/dashboard/incidents/{incident.id}/"
    
    def _get_severity_emoji(self, severity: str) -> str:
        """Get emoji for severity level."""
        emoji_map = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        return emoji_map.get(str(severity).lower(), "⚪")
    
    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for status."""
        emoji_map = {
            "open": "🆕",
            "acknowledged": "👀",
            "resolved": "✅",
        }
        return emoji_map.get(str(status).lower(), "❓")
    
    def _format_relative_time(self, dt) -> str:
        """Format datetime as relative time string."""
        if not dt:
            return "N/A"
        
        now = timezone.now()
        diff = now - dt
        
        minutes = int(diff.total_seconds() / 60)
        hours = int(minutes / 60)
        days = int(hours / 24)
        
        if days > 0:
            return f"il y a {days}j"
        if hours > 0:
            return f"il y a {hours}h"
        if minutes > 0:
            return f"il y a {minutes}min"
        return "à l'instant"


class OnCallService:
    """
    Service for on-call schedule queries from Slack.
    """
    
    async def get_current_oncall(self, team_id: str | None = None) -> SlackCommandResult:
        """
        Get current on-call personnel.
        
        Args:
            team_id: Optional team filter.
            
        Returns:
            SlackCommandResult with on-call info.
        """
        from core.models import OnCallSchedule
        
        now = timezone.now()
        
        query = OnCallSchedule.objects.filter(
            start_time__lte=now,
            end_time__gte=now,
        ).select_related("user", "team")
        
        if team_id:
            query = query.filter(team_id=team_id)
        
        schedules = [s async for s in query]
        
        if not schedules:
            return SlackCommandResult(
                success=True,
                text="⚠️ Aucune astreinte configurée actuellement.",
            )
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📞 Astreinte actuelle",
                    "emoji": True,
                },
            },
        ]
        
        for schedule in schedules:
            user = schedule.user
            team = schedule.team
            end_time = schedule.end_time.strftime("%d/%m %H:%M")
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{team.name}*\n"
                        f"👤 {user.get_full_name() or user.username}\n"
                        f"📧 {user.email}\n"
                        f"⏰ Jusqu'au {end_time}"
                    ),
                },
            })
        
        return SlackCommandResult(
            success=True,
            blocks=blocks,
        )
