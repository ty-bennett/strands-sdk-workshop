from strands.models import BedrockModel
from strands import Agent

from dotenv import load_dotenv
load_dotenv()


model = BedrockModel(model_id="amazon.nova-pro-v1:0")
model = BedrockModel(model_id="")
model = BedrockModel(model_id="amazon.nova-pro-v1:0")
model = BedrockModel(model_id="amazon.nova-pro-v1:0")

# agent
agent = Agent(model=model)

if __name__ == "__main__":
    agent("Give me a mean green apple pie recipe")
