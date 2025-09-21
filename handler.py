# handler.py
import runpod
from worker import handler as _handler

# Expose the handler function Runpod looks for:
def handler(event):
    return _handler(event)

# Start the Runpod loop when the container runs:
runpod.serverless.start({"handler": handler})
