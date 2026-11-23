from PIL import Image

img = Image.open(r"C:\Users\tangt\.gemini\antigravity\scratch\drvn-app\icon.png")
img.save(r"C:\Users\tangt\.gemini\antigravity\scratch\drvn-app\icon.ico", format="ICO", sizes=[(64, 64), (32, 32), (16, 16)])
print("Created icon.ico successfully!")
