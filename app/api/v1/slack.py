"""
IMAS Manager - Slack ChatOps API Views

Handles Slack slash commands and interactive components.
"""
from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from services.chatops import ChatOpsService, OnCallService

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class SlackSlashCommandView(View):
    """
    Handle Slack slash commands.
    
    Endpoint: POST /api/v1/slack/commands/
    
    Slack sends:
    - token: Verification token (deprecated, use signing secret)
    - command: The slash command (e.g., "/incident")
    - text: Arguments after the command
    - user_id: Slack user ID
    - user_name: Slack username
    - channel_id: Channel where command was invoked
    - response_url: URL for delayed responses
    """
    
    def post(self, request):
        """Handle incoming slash command."""
        chatops = ChatOpsService()
        
        # Verify request signature
        signature = request.headers.get("X-Slack-Signature", "")
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        
        if not chatops.verify_request(signature, timestamp, request.body):
            logger.warning("Invalid Slack signature for slash command")
            return JsonResponse({"error": "Invalid signature"}, status=401)
        
        # Parse form data
        try:
            # Slack sends application/x-www-form-urlencoded
            body = request.body.decode("utf-8")
            params = parse_qs(body)
            
            command_name = params.get("command", [""])[0]
            text = params.get("text", [""])[0]
            user_id = params.get("user_id", [""])[0]
            user_name = params.get("user_name", [""])[0]
            channel_id = params.get("channel_id", [""])[0]
            response_url = params.get("response_url", [""])[0]
            
        except Exception as e:
            logger.error(f"Failed to parse Slack command: {e}")
            return JsonResponse({"text": "❌ Erreur de parsing"}, status=400)
        
        logger.info(f"Slack command: {command_name} {text} from {user_name}")
        
        # Route based on command
        if command_name in ("/incident", "/inc"):
            return self._handle_incident_command(
                text, user_id, user_name, channel_id, response_url
            )
        elif command_name == "/oncall":
            return self._handle_oncall_command(
                text, user_id, channel_id
            )
        else:
            return JsonResponse({
                "response_type": "ephemeral",
                "text": f"❌ Commande inconnue: {command_name}",
            })
    
    def _handle_incident_command(
        self,
        text: str,
        user_id: str,
        user_name: str,
        channel_id: str,
        response_url: str,
    ) -> JsonResponse:
        """Handle /incident command."""
        chatops = ChatOpsService()
        
        # Parse the command
        command = chatops.parse_command(text)
        
        # Execute synchronously for immediate response
        # (For long operations, use response_url for async response)
        result = chatops.execute_command_sync(
            command=command,
            user_id=user_id,
            user_email=None,  # Would need to look up
            channel_id=channel_id,
        )
        
        response = {
            "response_type": result.response_type,
        }
        
        if result.blocks:
            response["blocks"] = result.blocks
        if result.text:
            response["text"] = result.text
        if result.attachments:
            response["attachments"] = result.attachments
        
        return JsonResponse(response)
    
    def _handle_oncall_command(
        self,
        text: str,
        user_id: str,
        channel_id: str,
    ) -> JsonResponse:
        """Handle /oncall command."""
        import asyncio
        
        oncall_service = OnCallService()
        
        # Parse optional team argument
        team_id = text.strip() if text.strip() else None
        
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                oncall_service.get_current_oncall(team_id)
            )
        finally:
            loop.close()
        
        response = {
            "response_type": "ephemeral",
        }
        
        if result.blocks:
            response["blocks"] = result.blocks
        if result.text:
            response["text"] = result.text
        
        return JsonResponse(response)


@method_decorator(csrf_exempt, name="dispatch")
class SlackInteractiveView(View):
    """
    Handle Slack interactive components (buttons, modals, etc.).
    
    Endpoint: POST /api/v1/slack/interactive/
    
    Slack sends a payload with:
    - type: "block_actions", "view_submission", etc.
    - user: User info
    - actions: List of actions triggered
    - trigger_id: For opening modals
    - response_url: For async responses
    """
    
    def post(self, request):
        """Handle interactive component action."""
        chatops = ChatOpsService()
        
        # Verify request signature
        signature = request.headers.get("X-Slack-Signature", "")
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        
        if not chatops.verify_request(signature, timestamp, request.body):
            logger.warning("Invalid Slack signature for interactive")
            return JsonResponse({"error": "Invalid signature"}, status=401)
        
        # Parse payload
        try:
            body = request.body.decode("utf-8")
            params = parse_qs(body)
            payload_str = params.get("payload", ["{}"])[0]
            payload = json.loads(payload_str)
        except Exception as e:
            logger.error(f"Failed to parse interactive payload: {e}")
            return JsonResponse({"error": "Parse error"}, status=400)
        
        payload_type = payload.get("type", "")
        
        if payload_type == "block_actions":
            return self._handle_block_actions(payload)
        elif payload_type == "view_submission":
            return self._handle_view_submission(payload)
        else:
            logger.warning(f"Unhandled payload type: {payload_type}")
            return JsonResponse({})
    
    def _handle_block_actions(self, payload: dict) -> JsonResponse:
        """Handle button clicks and other block actions."""
        actions = payload.get("actions", [])
        user = payload.get("user", {})
        user_id = user.get("id", "")
        
        for action in actions:
            action_id = action.get("action_id", "")
            value = action.get("value", "")
            
            if action_id == "ack_incident":
                return self._ack_incident(value, user_id)
            elif action_id == "resolve_incident":
                return self._resolve_incident(value, user_id)
            elif action_id == "escalate_incident":
                return self._escalate_incident(value, user_id)
        
        return JsonResponse({})
    
    def _ack_incident(self, incident_id: str, user_id: str) -> JsonResponse:
        """Acknowledge incident from button click."""
        from services.chatops import ChatOpsService, SlackCommand, SlackCommandType
        
        chatops = ChatOpsService()
        command = SlackCommand(
            action=SlackCommandType.ACK,
            args=[],
            incident_id=incident_id,
        )
        
        result = chatops.execute_command_sync(
            command=command,
            user_id=user_id,
        )
        
        # Update the original message
        return JsonResponse({
            "response_type": "in_channel",
            "replace_original": True,
            "text": result.text,
            "blocks": result.blocks,
        })
    
    def _resolve_incident(self, incident_id: str, user_id: str) -> JsonResponse:
        """Resolve incident from button click."""
        from services.chatops import ChatOpsService, SlackCommand, SlackCommandType
        
        chatops = ChatOpsService()
        command = SlackCommand(
            action=SlackCommandType.RESOLVE,
            args=["Résolu via bouton Slack"],
            incident_id=incident_id,
        )
        
        result = chatops.execute_command_sync(
            command=command,
            user_id=user_id,
        )
        
        return JsonResponse({
            "response_type": "in_channel",
            "replace_original": True,
            "text": result.text,
            "blocks": result.blocks,
        })
    
    def _escalate_incident(self, incident_id: str, user_id: str) -> JsonResponse:
        """Escalate incident from button click."""
        from services.chatops import ChatOpsService, SlackCommand, SlackCommandType
        
        chatops = ChatOpsService()
        command = SlackCommand(
            action=SlackCommandType.ESCALATE,
            args=[],
            incident_id=incident_id,
        )
        
        result = chatops.execute_command_sync(
            command=command,
            user_id=user_id,
        )
        
        return JsonResponse({
            "response_type": "in_channel",
            "replace_original": False,
            "text": result.text,
            "blocks": result.blocks,
        })
    
    def _handle_view_submission(self, payload: dict) -> JsonResponse:
        """Handle modal form submissions."""
        view = payload.get("view", {})
        callback_id = view.get("callback_id", "")
        
        if callback_id == "create_incident_modal":
            return self._handle_create_incident_modal(payload)
        
        return JsonResponse({})
    
    def _handle_create_incident_modal(self, payload: dict) -> JsonResponse:
        """Handle incident creation modal submission."""
        view = payload.get("view", {})
        values = view.get("state", {}).get("values", {})
        user = payload.get("user", {})
        user_id = user.get("id", "")
        
        # Extract form values
        title_block = values.get("title_block", {})
        title_input = title_block.get("title_input", {})
        title = title_input.get("value", "")
        
        description_block = values.get("description_block", {})
        description_input = description_block.get("description_input", {})
        description = description_input.get("value", "")
        
        severity_block = values.get("severity_block", {})
        severity_select = severity_block.get("severity_select", {})
        severity = severity_select.get("selected_option", {}).get("value", "medium")
        
        if not title:
            return JsonResponse({
                "response_action": "errors",
                "errors": {
                    "title_block": "Le titre est requis",
                },
            })
        
        # Create incident
        from core.models import Incident
        from core.models.incident import IncidentSeverity, IncidentStatus
        import asyncio
        
        severity_map = {
            "critical": IncidentSeverity.CRITICAL,
            "high": IncidentSeverity.HIGH,
            "medium": IncidentSeverity.MEDIUM,
            "low": IncidentSeverity.LOW,
        }
        
        try:
            loop = asyncio.new_event_loop()
            incident = loop.run_until_complete(
                Incident.objects.acreate(
                    title=title,
                    description=description or f"Créé depuis Slack par <@{user_id}>",
                    severity=severity_map.get(severity, IncidentSeverity.MEDIUM),
                    status=IncidentStatus.OPEN,
                )
            )
            loop.close()
            
            # Close modal with success
            return JsonResponse({
                "response_action": "clear",
            })
            
        except Exception as e:
            logger.error(f"Failed to create incident from modal: {e}")
            return JsonResponse({
                "response_action": "errors",
                "errors": {
                    "title_block": f"Erreur: {str(e)}",
                },
            })


@method_decorator(csrf_exempt, name="dispatch")
class SlackEventsView(View):
    """
    Handle Slack Events API.
    
    Endpoint: POST /api/v1/slack/events/
    
    Handles:
    - URL verification challenge
    - Event callbacks (mentions, messages, etc.)
    """
    
    def post(self, request):
        """Handle Slack event."""
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        
        event_type = payload.get("type", "")
        
        # Handle URL verification
        if event_type == "url_verification":
            challenge = payload.get("challenge", "")
            return JsonResponse({"challenge": challenge})
        
        # Verify signature for real events
        chatops = ChatOpsService()
        signature = request.headers.get("X-Slack-Signature", "")
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        
        if not chatops.verify_request(signature, timestamp, request.body):
            logger.warning("Invalid Slack signature for event")
            return JsonResponse({"error": "Invalid signature"}, status=401)
        
        # Handle event callback
        if event_type == "event_callback":
            event = payload.get("event", {})
            return self._handle_event(event)
        
        return JsonResponse({"ok": True})
    
    def _handle_event(self, event: dict) -> JsonResponse:
        """Route event to appropriate handler."""
        event_type = event.get("type", "")
        
        if event_type == "app_mention":
            return self._handle_app_mention(event)
        elif event_type == "message":
            return self._handle_message(event)
        
        return JsonResponse({"ok": True})
    
    def _handle_app_mention(self, event: dict) -> JsonResponse:
        """Handle when bot is mentioned."""
        text = event.get("text", "")
        user = event.get("user", "")
        channel = event.get("channel", "")
        
        # Extract command from mention (remove bot mention)
        import re
        clean_text = re.sub(r"<@\w+>", "", text).strip()
        
        if clean_text:
            # Treat as command
            chatops = ChatOpsService()
            command = chatops.parse_command(clean_text)
            result = chatops.execute_command_sync(
                command=command,
                user_id=user,
                channel_id=channel,
            )
            
            # Send response via API
            self._send_response(channel, result)
        
        return JsonResponse({"ok": True})
    
    def _handle_message(self, event: dict) -> JsonResponse:
        """Handle direct messages to bot."""
        # Only respond to DMs
        channel_type = event.get("channel_type", "")
        if channel_type != "im":
            return JsonResponse({"ok": True})
        
        # Ignore bot's own messages
        if event.get("bot_id"):
            return JsonResponse({"ok": True})
        
        text = event.get("text", "")
        user = event.get("user", "")
        channel = event.get("channel", "")
        
        # Treat as command
        chatops = ChatOpsService()
        command = chatops.parse_command(text)
        result = chatops.execute_command_sync(
            command=command,
            user_id=user,
            channel_id=channel,
        )
        
        self._send_response(channel, result)
        
        return JsonResponse({"ok": True})
    
    def _send_response(self, channel: str, result) -> None:
        """Send response message to channel."""
        from services.notifications.providers.slack import SlackProvider
        from core.models import NotificationProvider
        
        try:
            # Get active Slack provider
            provider_config = NotificationProvider.objects.filter(
                provider_type="SLACK",
                is_active=True,
            ).first()
            
            if not provider_config:
                logger.warning("No active Slack provider configured")
                return
            
            slack = SlackProvider(provider_config)
            client = slack._get_client()
            
            kwargs = {
                "channel": channel,
                "text": result.text or "Response",
            }
            
            if result.blocks:
                kwargs["blocks"] = result.blocks
            
            client.chat_postMessage(**kwargs)
            
        except Exception as e:
            logger.error(f"Failed to send Slack response: {e}")
