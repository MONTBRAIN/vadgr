"""OS accessibility API element locator."""

import logging
import shutil
import subprocess
from typing import Optional

from computer_use.core.types import Element, Platform, Region, ScreenState
from computer_use.grounding.base import ElementLocator

logger = logging.getLogger("computer_use.grounding.accessibility")


class AccessibilityLocator(ElementLocator):
    """Locate elements using OS accessibility APIs.

    - WSL2/Windows: UI Automation via PowerShell
    - macOS: pyobjc ApplicationServices / AXUIElementRef
    - Linux: AT-SPI2 via pyatspi or gdbus
    """

    def __init__(self, platform: Platform):
        self._platform = platform
        self._impl = self._load_impl()

    def _load_impl(self):
        match self._platform:
            case Platform.WSL2 | Platform.WINDOWS:
                return _WindowsA11y()
            case Platform.MACOS:
                return _MacOSA11y()
            case Platform.LINUX:
                return _LinuxA11y()

    def find_element(
        self, description: str, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        return self._impl.find_element(description)

    def find_all_elements(
        self, screen: Optional[ScreenState] = None
    ) -> list[Element]:
        return self._impl.find_all_elements()

    def find_element_at(
        self, x: int, y: int, screen: Optional[ScreenState] = None
    ) -> Optional[Element]:
        return self._impl.find_element_at(x, y)

    def is_available(self) -> bool:
        return self._impl.is_available()


class _WindowsA11y:
    """Windows UI Automation via PowerShell."""

    _FIND_SCRIPT = """
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "{name}"
)
$element = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
if ($element) {{
    $rect = $element.Current.BoundingRectangle
    Write-Output "$($element.Current.Name)|$($element.Current.ControlType.ProgrammaticName)|$($rect.X)|$($rect.Y)|$($rect.Width)|$($rect.Height)"
}} else {{
    Write-Output "NOT_FOUND"
}}
"""

    _FIND_AT_SCRIPT = """
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$point = New-Object System.Windows.Point({x}, {y})
$element = [System.Windows.Automation.AutomationElement]::FromPoint($point)
if ($element) {{
    $rect = $element.Current.BoundingRectangle
    Write-Output "$($element.Current.Name)|$($element.Current.ControlType.ProgrammaticName)|$($rect.X)|$($rect.Y)|$($rect.Width)|$($rect.Height)"
}} else {{
    Write-Output "NOT_FOUND"
}}
"""

    _FIND_ALL_SCRIPT = """
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condition = [System.Windows.Automation.Condition]::TrueCondition
$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)
foreach ($el in $elements) {
    $rect = $el.Current.BoundingRectangle
    Write-Output "$($el.Current.Name)|$($el.Current.ControlType.ProgrammaticName)|$($rect.X)|$($rect.Y)|$($rect.Width)|$($rect.Height)"
}
"""

    def is_available(self) -> bool:
        return shutil.which("powershell.exe") is not None

    def find_element(self, description: str) -> Optional[Element]:
        try:
            from computer_use.platform.wsl2 import _run_ps

            result = _run_ps(self._FIND_SCRIPT.format(name=description))
            if result == "NOT_FOUND" or not result:
                return None
            return self._parse_element(result)
        except Exception as e:
            logger.debug("Windows a11y find_element failed: %s", e)
            return None

    def find_all_elements(self) -> list[Element]:
        try:
            from computer_use.platform.wsl2 import _run_ps

            result = _run_ps(self._FIND_ALL_SCRIPT, timeout=10.0)
            if not result:
                return []
            elements = []
            for line in result.strip().split("\n"):
                el = self._parse_element(line.strip())
                if el:
                    elements.append(el)
            return elements
        except Exception as e:
            logger.debug("Windows a11y find_all failed: %s", e)
            return []

    def find_element_at(self, x: int, y: int) -> Optional[Element]:
        try:
            from computer_use.platform.wsl2 import _run_ps

            result = _run_ps(self._FIND_AT_SCRIPT.format(x=x, y=y))
            if result == "NOT_FOUND" or not result:
                return None
            return self._parse_element(result)
        except Exception as e:
            logger.debug("Windows a11y find_element_at failed: %s", e)
            return None

    def _parse_element(self, line: str) -> Optional[Element]:
        parts = line.split("|")
        if len(parts) < 6:
            return None
        try:
            name = parts[0]
            role = parts[1].replace("ControlType.", "")
            x = int(float(parts[2]))
            y = int(float(parts[3]))
            width = int(float(parts[4]))
            height = int(float(parts[5]))
            return Element(
                name=name,
                role=role,
                region=Region(x=x, y=y, width=width, height=height),
                confidence=1.0,
                source="accessibility",
            )
        except (ValueError, IndexError):
            return None


class _MacOSA11y:
    """macOS Accessibility API stub."""

    def is_available(self) -> bool:
        try:
            import AppKit  # noqa: F401

            return True
        except ImportError:
            return False

    def find_element(self, description: str) -> Optional[Element]:
        # TODO: Implement via pyobjc AXUIElement
        logger.debug("macOS accessibility find_element not yet implemented")
        return None

    def find_all_elements(self) -> list[Element]:
        logger.debug("macOS accessibility find_all not yet implemented")
        return []

    def find_element_at(self, x: int, y: int) -> Optional[Element]:
        logger.debug("macOS accessibility find_element_at not yet implemented")
        return None


class _LinuxA11y:
    """Linux AT-SPI2 accessibility stub."""

    def is_available(self) -> bool:
        try:
            import pyatspi  # noqa: F401

            return True
        except ImportError:
            return False

    def find_element(self, description: str) -> Optional[Element]:
        # TODO: Implement via AT-SPI2
        logger.debug("Linux accessibility find_element not yet implemented")
        return None

    def find_all_elements(self) -> list[Element]:
        logger.debug("Linux accessibility find_all not yet implemented")
        return []

    def find_element_at(self, x: int, y: int) -> Optional[Element]:
        logger.debug("Linux accessibility find_element_at not yet implemented")
        return None
