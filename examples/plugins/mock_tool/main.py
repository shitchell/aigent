from langchain_core.tools import tool

@tool
def get_current_weather(location: str) -> str:
    """Get the current weather in a given location."""
    return f"The weather in {location} is sunny and 72 degrees."
