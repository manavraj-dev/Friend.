from pathlib import Path

DEFAULT_VAULT_ROOT = Path("vault")

VAULT_DIRECTORIES = [
    "daily",
    "people",
    "projects",
    "themes",
    "secrets",
    "core",
    "core/_proposed",
    "_meta",
    "_meta/file.locks",
]
