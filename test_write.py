import sys
import torch

# Create a dummy tensor
out = torch.ones((10,), dtype=torch.uint8) * 65 # 'A'

# Write its memoryview to stdout directly
sys.stdout.buffer.write(out.numpy())
