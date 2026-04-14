from strands.models import BedrockModel
from strands import Agent

from dotenv import load_dotenv
load_dotenv()


model = BedrockModel(model_id="amazon.nova-pro-v1:0")
# model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")
# model = BedrockModel(model_id="deepseek.v3.2")

# agent
agent = Agent(model=model)

if __name__ == "__main__":
    agent("Give me a mean green apple pie recipe")
