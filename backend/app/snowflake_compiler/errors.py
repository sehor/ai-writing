"""Shared errors for the Snowflake compiler."""


class ArtifactNotParseableError(ValueError):
    """The artifact contained no structure the compiler could use.

    Raised *before* anything is persisted so a failed parse can never
    pollute the database; routers map it to HTTP 422.
    """
