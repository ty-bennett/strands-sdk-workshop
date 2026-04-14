from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel
from dotenv import load_dotenv
load_dotenv()


# @tool turns a regular Python function into something the agent can call.
# The docstring is what the agent reads to decide when and why to use it.
@tool
def get_current_time() -> str:
    """Returns the current date and time so the agent knows when it is."""
    return datetime.now().strftime("It's %A, %B %d %Y at %I:%M %p")


# Pass the tool in a list — the agent will call it automatically when needed.
agent = Agent(
    model=BedrockModel
    (
        model_id="amazon.nova-pro-v1:0"),
    tools=[get_current_time],
)

if __name__ == "__main__":
    # Without the tool, the model has no idea what time it is.
    # With it, the agent calls get_current_time() and uses the result.
    agent("What time is it currently?")
