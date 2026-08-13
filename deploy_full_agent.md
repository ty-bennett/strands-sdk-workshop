.venv/bin/agentcore configure \
  --create \
  --name my_new_agent \
  --entrypoint agent_core_agent_full.py \
  --runtime PYTHON_3_13 \
  --execution-role arn:aws:iam::970547346077:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1-3d48f4ac55 \
  --requirements-file requirements-agentcore.txt \
  --region us-east-1 \
  --non-interactive

.venv/bin/agentcore deploy --agent my_new_agent
