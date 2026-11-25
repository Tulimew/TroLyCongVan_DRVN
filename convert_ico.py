import os
from PIL import Image

current_dir = os.path.dirname(os.path.abspath(__file__))
png_path = os.path.join(current_dir, "icon.png")
ico_path = os.path.join(current_dir, "icon.ico")

img = Image.open(png_path)
img.save(ico_path, format="ICO", sizes=[(64, 64), (32, 32), (16, 16)])
print(f"Created icon.ico successfully at {ico_path}!")
