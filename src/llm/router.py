"""LLM model router based on task complexity."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def route_model(
    report_type: str, 
    requested_model: str, 
    provider: str,
    override_model: Optional[str] = None
) -> str:
    """Determine the optimal model based on the task type.
    
    Args:
        report_type: The type of report being generated (hỏi đáp, phân tích, etc.)
        requested_model: The default model from configuration
        provider: The LLM provider (openai, google)
        override_model: An explicit override (if any)
        
    Returns:
        The model identifier to use.
    """
    if override_model:
        return override_model

    is_complex = report_type == "phân tích"
    
    if provider == "openai":
        if is_complex:
            # Complex synthesis requires higher reasoning
            if requested_model == "gpt-4o-mini":
                logger.info("Routing from gpt-4o-mini to gpt-4o for complex analysis")
                return "gpt-4o"
        else:
            # Simple tasks can be downgraded for speed/cost
            if requested_model == "gpt-4o":
                logger.info("Routing from gpt-4o to gpt-4o-mini for simple Q&A")
                return "gpt-4o-mini"
                
    elif provider == "google":
        if is_complex:
            if "flash" in requested_model:
                logger.info("Routing from flash to pro for complex analysis")
                return "gemini-1.5-pro"
        else:
            if "pro" in requested_model:
                logger.info("Routing from pro to flash for simple Q&A")
                return "gemini-1.5-flash"
                
    return requested_model
