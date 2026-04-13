from enum import IntEnum


class AccessRole(IntEnum):
    """Hierarchical access roles for API authentication.

    Higher values grant more permissions.  Each role implicitly includes
    all permissions of lower roles.
    """

    READER = 1
    NOTIFICATION_OPERATOR = 2
    ADMIN = 3
