from strands.models import ollama
from strands import Agent
from strands.models.ollama import OllamaModel
from strands.models import BedrockModel


from dotenv import load_dotenv
load_dotenv()


# Bedrock alternatives (all currently Active):
# model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")  # cheapest, what the rest of the workshop uses
# model = BedrockModel(model_id="us.anthropic.claude-sonnet-5")                 # more capable, ~higher cost
# model = BedrockModel(model_id="arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0")
model = BedrockModel(model_id="arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0")
# model = BedrockModel(model_id="deepseek.v3.2")                                # ID unverified

# Create an Ollama model instance
# model = OllamaModel(
#    host="http://localhost:11434",  # Ollama server address
#    model_id="llama3.1"               # Specify which model to use
#)

# Create an agent using the Ollama model
agent = Agent(model=model,
              system_prompt="You are Yoda. Please respond with the same sentence structure as Yoda")
# agent

if __name__ == "__main__":
    agent("Give me a apple pie recipe")
