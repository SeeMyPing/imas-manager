"""
IMAS Manager - Base Notification Provider

Abstract base class for all notification providers.
Implements the Strategy pattern for interchangeable notification backends.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models import NotificationProvider


class BaseNotificationProvider(ABC):
    """
    Abstract base class for notification providers.
    
    All notification providers (Slack, Discord, SMS, Email) must inherit
    from this class and implement the required methods.
    
    Usage:
        provider = SlackProvider(notification_provider_instance)
        await provider.send(recipient="C0123456789", message=message)
    """

    def __init__(self, config: "NotificationProvider") -> None:
        """
        Initialize the provider with configuration.
        
        Args:
            config: NotificationProvider model instance containing
                    provider-specific configuration in the config JSONField.
        """
        self.config = config
        self.name = config.name
        self.provider_type = config.type
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """
        Validate that required configuration keys are present.
        
        Raises:
            ValueError: If required configuration is missing.
        """
        pass

    @abstractmethod
    def send(
        self,
        recipient: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a notification to a single recipient.
        
        Args:
            recipient: Channel ID, phone number, email, etc.
            message: Message content dict with 'title', 'body', etc.
            
        Returns:
            True if sent successfully, False otherwise.
        """
        pass

    @abstractmethod
    def send_batch(
        self,
        recipients: list[str],
        message: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send notifications to multiple recipients.
        
        Args:
            recipients: List of recipient identifiers.
            message: Message content dict.
            
        Returns:
            Dict mapping recipient to success status.
        """
        pass

    def get_config_value(self, key: str, required: bool = False) -> Any:
        """
        Safely get a configuration value.
        
        Args:
            key: Configuration key.
            required: If True, raise ValueError if key is missing.
            
        Returns:
            Configuration value or None.
            
        Raises:
            ValueError: If required key is missing.
        """
        value = self.config.config.get(key)
        if required and value is None:
            raise ValueError(
                f"Required configuration '{key}' missing for provider '{self.name}'"
            )
        return value

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}')>"


class NotificationProviderFactory:
    """
    Factory for creating notification provider instances.
    
    Usage:
        provider = NotificationProviderFactory.create(notification_provider_model)
    """
    
    _providers: dict[str, type[BaseNotificationProvider]] = {}

    @classmethod
    def register(cls, provider_type: str, provider_class: type[BaseNotificationProvider]) -> None:
        """Register a provider class for a type."""
        cls._providers[provider_type] = provider_class

    @classmethod
    def create(cls, config: "NotificationProvider") -> BaseNotificationProvider:
        """
        Create a provider instance from configuration.
        
        Args:
            config: NotificationProvider model instance.
            
        Returns:
            Configured provider instance.
            
        Raises:
            ValueError: If provider type is not registered.
        """
        provider_class = cls._providers.get(config.type)
        if not provider_class:
            raise ValueError(f"Unknown provider type: {config.type}")
        return provider_class(config)

    @classmethod
    def get_available_types(cls) -> list[str]:
        """Get list of registered provider types."""
        return list(cls._providers.keys())
