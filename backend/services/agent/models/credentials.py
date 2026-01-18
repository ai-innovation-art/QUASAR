"""
Credential Manager for AI Agent

Handles:
- Loading credentials from .env
- Multi-credential support (2 keys per provider)
- Round-robin rotation when rate limited
- Easy to add new providers
"""

import os
from typing import Dict, Optional, Any
from dataclasses import dataclass
from dotenv import load_dotenv
import logging

# Setup logger
logger = logging.getLogger("credentials")

# Load environment variables
load_dotenv()


@dataclass
class Credential:
    """Single credential entry."""
    key: str
    remaining_quota: int = 10000  # Estimated
    is_active: bool = True
    

@dataclass 
class ProviderCredentials:
    """Credentials for a provider (supports multiple keys)."""
    current_index: int = 0
    credentials: list = None
    
    def __post_init__(self):
        if self.credentials is None:
            self.credentials = []


class CredentialManager:
    """
    Manages API credentials for all providers.
    
    Features:
    - Load from .env file
    - Multiple keys per provider (for higher rate limits)
    - Round-robin rotation
    - Fallback to next credential when rate limited
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern - only one instance needed."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._providers: Dict[str, ProviderCredentials] = {}
        self._load_credentials()
    
    def _load_credentials(self):
        """Load credentials from environment variables."""
        logger.info("🔑 Loading credentials from .env...")
        
        # Cerebras
        cerebras_creds = ProviderCredentials()
        for i in [1, 2]:
            key = os.getenv(f"CEREBRAS_API_KEY_{i}")
            if key:
                cerebras_creds.credentials.append(Credential(key=key))
        self._providers["cerebras"] = cerebras_creds
        logger.info(f"  Cerebras: {len(cerebras_creds.credentials)} keys loaded")
        
        # Groq
        groq_creds = ProviderCredentials()
        for i in [1, 2]:
            key = os.getenv(f"GROQ_API_KEY_{i}")
            if key:
                groq_creds.credentials.append(Credential(key=key))
        self._providers["groq"] = groq_creds
        logger.info(f"  Groq: {len(groq_creds.credentials)} keys loaded")
        
        # Cloudflare (needs account_id + token)
        cloudflare_creds = ProviderCredentials()
        for i in [1, 2]:
            account_id = os.getenv(f"CLOUDFLARE_ACCOUNT_ID_{i}")
            token = os.getenv(f"CLOUDFLARE_API_TOKEN_{i}")
            if account_id and token:
                # Store as dict for cloudflare
                cloudflare_creds.credentials.append(
                    Credential(key=f"{account_id}:{token}")
                )
        self._providers["cloudflare"] = cloudflare_creds
        
        # Ollama - no credentials needed (local)
        self._providers["ollama"] = ProviderCredentials(
            credentials=[Credential(key="local", remaining_quota=999999)]
        )
    
    def get_credential(self, provider: str) -> Optional[str]:
        """
        Get current credential for a provider.
        
        Returns:
            API key string, or None if no credentials available
        """
        provider_creds = self._providers.get(provider)
        if not provider_creds or not provider_creds.credentials:
            return None
        
        current = provider_creds.current_index
        if current < len(provider_creds.credentials):
            cred = provider_creds.credentials[current]
            if cred.is_active:
                return cred.key
        
        return None
    
    def get_cloudflare_credentials(self) -> Optional[tuple]:
        """
        Get Cloudflare credentials (account_id, token).
        
        Returns:
            Tuple of (account_id, token) or None
        """
        key = self.get_credential("cloudflare")
        if key and ":" in key:
            return tuple(key.split(":", 1))
        return None
    
    def rotate_credential(self, provider: str) -> bool:
        """
        Rotate to next credential (when rate limited).
        
        Returns:
            True if successfully rotated, False if no more credentials
        """
        provider_creds = self._providers.get(provider)
        if not provider_creds:
            return False
        
        # Mark current as inactive
        current = provider_creds.current_index
        if current < len(provider_creds.credentials):
            provider_creds.credentials[current].is_active = False
        
        # Try next credential
        next_index = (current + 1) % len(provider_creds.credentials)
        if next_index == current:
            return False  # No other credentials
            
        if provider_creds.credentials[next_index].is_active:
            provider_creds.current_index = next_index
            return True
            
        return False
    
    def is_provider_available(self, provider: str) -> bool:
        """Check if provider has available credentials."""
        if provider == "ollama":
            return True  # Always available (local)
            
        provider_creds = self._providers.get(provider)
        if not provider_creds or not provider_creds.credentials:
            return False
            
        return any(c.is_active for c in provider_creds.credentials)
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all credentials (for health check)."""
        status = {}
        for name, provider_creds in self._providers.items():
            total = len(provider_creds.credentials)
            active = sum(1 for c in provider_creds.credentials if c.is_active)
            status[name] = {
                "available": active > 0,
                "total_keys": total,
                "active_keys": active,
                "has_credentials": total > 0
            }
        return status
    
    def reset_credentials(self):
        """Reset all credentials to active (for daily reset)."""
        for provider_creds in self._providers.values():
            for cred in provider_creds.credentials:
                cred.is_active = True
                cred.remaining_quota = 10000
