"""Exception hierarchy for the computer use engine."""


class ComputerUseError(Exception):
    """Base exception for all computer use engine errors."""


class ScreenCaptureError(ComputerUseError):
    """Screenshot capture failed."""


class ActionError(ComputerUseError):
    """Action execution failed."""


class ActionTimeoutError(ActionError):
    """Action did not complete within the timeout."""


class GroundingError(ComputerUseError):
    """Element grounding or location failed."""


class ElementNotFoundError(GroundingError):
    """Requested UI element was not found."""


class ProviderError(ComputerUseError):
    """LLM provider call failed."""


class ConfigError(ComputerUseError):
    """Configuration is invalid or missing."""


class PlatformNotSupportedError(ComputerUseError):
    """Current platform is not supported or not implemented."""
