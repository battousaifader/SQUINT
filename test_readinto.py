import torch
import io
import time

buffer = io.BytesIO(b'x' * 1000)
pinned_in = torch.empty(1000, dtype=torch.uint8, pin_memory=False) # mock
numpy_view = pinned_in.numpy()

t0 = time.time()
bytes_read = buffer.readinto(numpy_view)
print("Bytes read:", bytes_read)
print("Buffer content:", pinned_in[:10])
