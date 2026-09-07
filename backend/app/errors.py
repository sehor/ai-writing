"""Application failures independent of transport and dependency wiring."""


class ApplicationError(Exception):
    def __init__(self, detail: str | dict[str, object]):
        super().__init__(detail)
        self.detail = detail


class ResourceNotFoundError(ApplicationError):
    pass


class StateConflictError(ApplicationError):
    pass


class InvalidOperationError(ApplicationError):
    pass


class ProviderConfigurationError(ApplicationError):
    pass


class ProviderExecutionError(ApplicationError):
    pass
