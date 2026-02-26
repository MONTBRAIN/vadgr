"""The autonomous execution loop: screenshot -> decide -> act -> verify."""

import logging
import time
from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import Element, StepResult
from computer_use.grounding.base import ElementLocator
from computer_use.providers.base import AgentDecision, VisionProvider

logger = logging.getLogger("computer_use.loop")

MAX_CONSECUTIVE_FAILURES = 3
ACTION_DELAY_SECONDS = 0.5
RETRY_DELAY_SECONDS = 1.0


def run_core_loop(
    capture: ScreenCapture,
    executor: ActionExecutor,
    locator: Optional[ElementLocator],
    provider: VisionProvider,
    task: str,
    max_steps: int = 50,
    verify: bool = True,
    history: Optional[list[dict]] = None,
) -> list[StepResult]:
    """Run the autonomous loop until task is complete or limits are hit.

    Returns a list of StepResult objects, one per iteration.
    """
    if history is None:
        history = []
    results: list[StepResult] = []
    consecutive_failures = 0

    logger.info("Starting task: %s (max %d steps)", task, max_steps)

    for step_num in range(max_steps):
        logger.info("Step %d/%d", step_num + 1, max_steps)

        # 1. SCREENSHOT
        screen_before = capture.capture_full()
        logger.debug(
            "Screenshot: %dx%d, %d bytes",
            screen_before.width,
            screen_before.height,
            len(screen_before.image_bytes),
        )

        # 2. GROUND (find visible elements for context)
        elements: list[Element] = []
        if locator and locator.is_available():
            try:
                elements = locator.find_all_elements(screen_before)
                logger.debug("Found %d UI elements", len(elements))
            except Exception as e:
                logger.warning("Grounding failed, continuing without elements: %s", e)

        # 3. DECIDE (ask LLM what to do)
        try:
            decision: AgentDecision = provider.decide_action(
                screen=screen_before,
                task=task,
                history=history,
                elements=elements,
            )
            logger.info(
                "Decision: %s (confidence: %.2f, reasoning: %s)",
                decision.action.action_type.value,
                decision.confidence,
                decision.reasoning[:100],
            )
        except Exception as e:
            logger.error("Provider decision failed: %s", e)
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Too many consecutive failures, aborting.")
                break
            time.sleep(RETRY_DELAY_SECONDS)
            continue

        # 4. CHECK COMPLETION
        if decision.is_task_complete:
            logger.info("Task marked complete: %s", decision.reasoning)
            results.append(
                StepResult(
                    action_taken=decision.action,
                    screenshot_before=screen_before,
                    screenshot_after=screen_before,
                    success=True,
                    reasoning=decision.reasoning,
                )
            )
            break

        # 5. ACT
        try:
            executor.execute_action(decision.action)
            logger.debug("Action executed: %s", decision.action.action_type.value)
        except Exception as e:
            logger.error("Action execution failed: %s", e)
            results.append(
                StepResult(
                    action_taken=decision.action,
                    screenshot_before=screen_before,
                    screenshot_after=screen_before,
                    success=False,
                    reasoning=decision.reasoning,
                    error=str(e),
                )
            )
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Too many consecutive failures, aborting.")
                break
            continue

        # 6. WAIT for UI to settle
        time.sleep(ACTION_DELAY_SECONDS)

        # 7. VERIFY
        screen_after = capture.capture_full()
        success = True
        error_msg = None

        if verify and decision.reasoning:
            try:
                success, explanation = provider.verify_action(
                    before=screen_before,
                    after=screen_after,
                    expected=decision.reasoning,
                )
                if not success:
                    error_msg = f"Verification failed: {explanation}"
                    logger.warning(error_msg)
            except Exception as e:
                logger.warning("Verification call failed: %s", e)
                # Don't count verification failures as action failures
                success = True

        # 8. RECORD
        step_result = StepResult(
            action_taken=decision.action,
            screenshot_before=screen_before,
            screenshot_after=screen_after,
            success=success,
            reasoning=decision.reasoning,
            error=error_msg,
            elements_found=elements,
        )
        results.append(step_result)

        # Update history for next iteration
        history.append(
            {
                "step": step_num + 1,
                "action": f"{decision.action.action_type.value}"
                + (f" at ({decision.action.x},{decision.action.y})" if decision.action.x is not None else ""),
                "reasoning": decision.reasoning,
                "success": success,
                "error": error_msg,
            }
        )

        # Reset or increment failure counter
        if success:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Too many consecutive failures, aborting.")
                break

    logger.info(
        "Task finished: %d steps, %d successful",
        len(results),
        sum(1 for r in results if r.success),
    )
    return results
