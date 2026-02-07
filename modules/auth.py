"""
OAuth 2.1 / OIDC authentication module for remote MCP connections.

This module provides JWT validation using JWKS from an external authorization server
(e.g., Authentik) to secure remote access to the MCP server.
"""

import os
import json
import jwt
import requests
from typing import Optional, Dict, Any
from functools import lru_cache
from datetime import datetime, timedelta


class OAuthConfig:
    """Configuration for OAuth authentication."""
    
    def __init__(self):
        self._loaded = False
        self._enabled = None
        self._issuer = None
        self._server_url = None
        self._jwks_cache_ttl = None
    
    def _load(self):
        """Lazy load configuration from environment variables."""
        if not self._loaded:
            self._enabled = os.getenv("MCP_OAUTH_ENABLED", "false").lower() == "true"
            self._issuer = os.getenv("MCP_OAUTH_ISSUER", "")
            self._server_url = os.getenv("MCP_SERVER_URL", "")
            self._jwks_cache_ttl = int(os.getenv("MCP_OAUTH_JWKS_CACHE_TTL", "3600"))
            self._loaded = True
            
    def reload(self):
        """Explicitly reset configuration to force a reload from environment."""
        self._loaded = False
        self._load()
    
    @property
    def enabled(self):
        self._load()
        return self._enabled
    
    @property
    def issuer(self):
        self._load()
        return self._issuer
    
    @property
    def server_url(self):
        self._load()
        return self._server_url
    
    @property
    def jwks_cache_ttl(self):
        self._load()
        return self._jwks_cache_ttl

    @property
    def audience(self):
        return self.server_url
    
    @property
    def resource_server_url(self):
        return self.server_url
        
    def is_valid(self) -> bool:
        """Check if OAuth configuration is valid."""
        if not self.enabled:
            return True
        return bool(self.issuer and self.server_url)


# Global config instance
oauth_config = OAuthConfig()


@lru_cache(maxsize=1)
def get_jwks_uri(issuer: str) -> str:
    """
    Fetch the JWKS URI from the OIDC discovery endpoint.
    
    Args:
        issuer: The OAuth issuer URL
        
    Returns:
        JWKS URI string
    """
    discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    try:
        response = requests.get(discovery_url, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        return metadata.get("jwks_uri", "")
    except Exception as e:
        raise ValueError(f"Failed to fetch OIDC discovery metadata: {str(e)}")


class JWKSCache:
    """Cache for JWKS keys with TTL."""
    
    def __init__(self, ttl_seconds: Optional[int] = None):
        self._ttl_seconds = ttl_seconds
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        
    def get_jwks(self, jwks_uri: str) -> Dict[str, Any]:
        """
        Fetch JWKS from the URI, using cache if valid.
        
        Args:
            jwks_uri: The JWKS endpoint URI
            
        Returns:
            JWKS dictionary
        """
        now = datetime.now()
        
        # Check if cache is valid
        if self._cache and self._cache_time:
            ttl = self._ttl_seconds if self._ttl_seconds is not None else oauth_config.jwks_cache_ttl
            if (now - self._cache_time) < timedelta(seconds=ttl):
                return self._cache
        
        # Fetch fresh JWKS
        try:
            response = requests.get(jwks_uri, timeout=10)
            response.raise_for_status()
            self._cache = response.json()
            self._cache_time = now
            return self._cache
        except Exception as e:
            raise ValueError(f"Failed to fetch JWKS: {str(e)}")


# Global JWKS cache - uses dynamic TTL from oauth_config if not specified
jwks_cache = JWKSCache()


def validate_token(token: str) -> Dict[str, Any]:
    """
    Validate a JWT access token using JWKS from the configured issuer.
    
    Args:
        token: The JWT access token to validate
        
    Returns:
        Decoded token payload if valid
        
    Raises:
        ValueError: If token is invalid or configuration is missing
    """
    if not oauth_config.is_valid():
        raise ValueError("OAuth is not properly configured")
    
    try:
        # Get JWKS URI from discovery
        jwks_uri = get_jwks_uri(oauth_config.issuer)
        if not jwks_uri:
            raise ValueError("JWKS URI not found in OIDC metadata")
        
        # Fetch JWKS with our cache (uses requests with proper headers)
        jwks = jwks_cache.get_jwks(jwks_uri)
        
        # Decode token header to get the key id (kid)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        # Find the matching key in JWKS
        signing_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                from jwt import algorithms
                signing_key = algorithms.RSAAlgorithm.from_jwk(key)
                break
        
        if not signing_key:
            raise ValueError(f"No matching key found for kid: {kid}")
        
        # Validate token - skip audience check since Authentik sets aud to client_id
        payload = jwt.decode(
            token,
            signing_key,  # RSAAlgorithm.from_jwk returns the key directly
            algorithms=["RS256", "ES256"],
            issuer=oauth_config.issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False,  # Authentik sets aud to client_id, not resource server
                "verify_iss": True
            }
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidAudienceError:
        raise ValueError("Invalid token audience")
    except jwt.InvalidIssuerError:
        raise ValueError("Invalid token issuer")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {str(e)}")
    except Exception as e:
        raise ValueError(f"Token validation failed: {str(e)}")


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """
    Extract Bearer token from Authorization header.
    
    Args:
        authorization_header: The Authorization header value
        
    Returns:
        The token string if found, None otherwise
    """
    if not authorization_header:
        return None
    
    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    return parts[1]


def get_protected_resource_metadata() -> Dict[str, Any]:
    """
    Generate OAuth 2.0 Protected Resource Metadata (RFC 9728).
    
    Returns:
        Metadata dictionary
    """
    return {
        "resource": oauth_config.resource_server_url,
        "authorization_servers": [oauth_config.server_url],  # Point to MCP server, not Authentik
        "bearer_methods_supported": ["header"],
        "resource_signing_alg_values_supported": ["RS256", "ES256"],
        "resource_documentation": "https://github.com/vladimir-tutin/plex-mcp-server"
    }


def get_www_authenticate_header() -> str:
    """
    Generate WWW-Authenticate header for 401 responses (RFC 9728).
    
    Returns:
        WWW-Authenticate header value
    """
    metadata_url = f"{oauth_config.resource_server_url.rstrip('/')}/.well-known/oauth-protected-resource"
    return f'Bearer resource_metadata="{metadata_url}"'
