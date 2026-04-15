from enum import IntEnum


class AccessRole(IntEnum):
    """Hierarchical access roles for API authentication.

    Higher values grant more permissions.  Each role implicitly includes
    all permissions of lower roles.
    """

    READER = 100
    NOTIFICATION_OPERATOR = 200
    ADMIN = 300

    def display_name(self) -> str:
        """Return a human-friendly display name for this role."""
        return self.name.replace("_", " ").title()
