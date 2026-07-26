from PIL import Image
import numpy as np

img_in = np.array(Image.open('/home/fader/.gemini/antigravity-cli/brain/cd783ba0-9b4b-45a6-a786-d8bf834e0fcc/input_frame.jpg'))
img_out = np.array(Image.open('/home/fader/.gemini/antigravity-cli/brain/cd783ba0-9b4b-45a6-a786-d8bf834e0fcc/output_frame.jpg'))

print("Input mean RGB:", np.mean(img_in, axis=(0,1)))
print("Output mean RGB:", np.mean(img_out, axis=(0,1)))

