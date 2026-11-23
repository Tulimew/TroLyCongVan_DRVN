from PIL import Image, ImageDraw

def create_icon():
    # Tạo icon 64x64 màu xanh lam với chữ CV (Công Văn)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Vẽ hình tròn nền xanh
    draw.ellipse((2, 2, 62, 62), fill=(14, 116, 144, 255), outline=(56, 189, 248, 255), width=2)
    
    # Vẽ biểu tượng trang giấy / chuông
    draw.rectangle((20, 16, 44, 48), fill=(255, 255, 255, 255))
    draw.line((24, 24, 40, 24), fill=(14, 116, 144, 255), width=2)
    draw.line((24, 30, 40, 30), fill=(14, 116, 144, 255), width=2)
    draw.line((24, 36, 36, 36), fill=(14, 116, 144, 255), width=2)
    
    # Chấm đỏ thông báo nhỏ ở góc
    draw.ellipse((42, 6, 58, 22), fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=2)
    
    img.save("C:\\Users\\tangt\\.gemini\\antigravity\\scratch\\drvn-app\\icon.png", "PNG")
    print("Created icon.png successfully!")

if __name__ == "__main__":
    create_icon()
