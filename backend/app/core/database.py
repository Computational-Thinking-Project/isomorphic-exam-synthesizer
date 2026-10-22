"""Database client factory for Supabase integration.

Provides authenticated client (respects RLS based on user JWT)
and service_role client (bypasses RLS, for admin/background operations).
"""

from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app.core.config import settings


def get_supabase_client() -> Client:
    """Return standard Supabase client with anon key."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be configured")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


@lru_cache(maxsize=1)
def get_service_role_client() -> Client:
    """Return privileged Supabase client with service_role key (bypasses RLS).

    Use ONLY for:
    - Background workers
    - Security event logging
    - Administrative operations & resource ownership verification
    """
    key = settings.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
    if not settings.SUPABASE_URL or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured")
    return create_client(settings.SUPABASE_URL, key)


def get_authenticated_client(access_token: str) -> Client:
    """Create a Supabase client authenticated as the end-user via JWT.

    Applies the user's JWT to all requests, ensuring PostgreSQL Row-Level
    Security (RLS) policies are automatically enforced.
    """
    if not access_token:
        raise ValueError("access_token is required to create authenticated client")
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be configured")

    headers = {"Authorization": f"Bearer {access_token}"}
    options = ClientOptions(headers=headers)
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY, options=options)

    # Explicitly configure PostgREST client with user JWT
    if hasattr(client, "postgrest") and hasattr(client.postgrest, "auth"):
        client.postgrest.auth(access_token)

    return client
