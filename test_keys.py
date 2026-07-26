import torch
sd = torch.load('/mnt/2tb/Video Upscaler/Real-CUGAN/up2x-latest-conservative.pth', map_location='cpu')
print("Keys:", list(sd.keys())[:10])
