"""Per-user platform credentials. Sensitive blobs encrypted via services.auth.crypto."""
from services.credentials.router import router
from services.credentials.store import (
    delete_credential,
    get_linkedin_credential,
    get_smtp_to_address,
    get_substack_credential,
    save_linkedin_credential,
    save_substack_credential,
)

__all__ = [
    "router",
    "get_linkedin_credential",
    "get_substack_credential",
    "get_smtp_to_address",
    "save_linkedin_credential",
    "save_substack_credential",
    "delete_credential",
]
