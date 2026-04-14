from datetime import datetime
from strands import Agent, tool
from strands.models import BedrockModel
from dotenv import load_dotenv
load_dotenv()


@tool
def get_current_time() -> str:
    """Returns the current date and time so the agent knows when it is."""
    return datetime.now().strftime("It's %A, %B %d %Y at %I:%M %p")


agent = Agent(
    model=BedrockModel(model_id="amazon.nova-pro-v1:0"),
    tools=[get_current_time],
)

if __name__ == "__main__":
    agent("What time is it currently?")
