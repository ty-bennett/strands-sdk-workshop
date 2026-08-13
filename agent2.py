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

        # model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")  # cheapest, what the rest of the workshop uses
        # model = BedrockModel(model_id="us.anthropic.claude-sonnet-5")                 # more capable, ~higher cost
        # model = BedrockModel(model_id="amazon.nova-2-lite-v1:0)
        # model = BedrockModel(model_id="deepseek.v3.2")                                # ID unverified
        # model_id="us.anthropic.claude-sonnet-5"),
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    tools=[get_current_time],
    system_prompt="You are Forrest Gump from the movie, Forrest Gump, please respond as if you are Forrest and use grammer similar to him"
)

if __name__ == "__main__":
    # Without the tool, the model has no idea what time it is.
    # With it, the agent calls get_current_time() and uses the result.
    agent("What time is it?")
