import os
import cv2
import numpy as np

out_dir = "OCR/text_renderer/backgrounds"
os.makedirs(out_dir, exist_ok=True)

def generate_background(width=640, height=480):
    # Base blanche
    img = np.ones((height, width, 3), dtype=np.uint8) * 255

    # Ajouter du bruit gaussien
    noise = np.random.normal(0, 25, img.shape).astype(np.uint8)
    img = cv2.add(img, noise)

    # Ajouter un dégradé pour simuler du papier jauni
    gradient = np.tile(np.linspace(230, 255, width, dtype=np.uint8), (height, 1))
    gradient = cv2.merge([gradient, gradient, gradient])
    img = cv2.addWeighted(img, 0.7, gradient, 0.3, 0)

    # Ajouter quelques taches grises
    for _ in range(10):
        x, y = np.random.randint(0, width), np.random.randint(0, height)
        r = np.random.randint(10, 40)
        color = np.random.randint(180, 230)
        cv2.circle(img, (x, y), r, (color, color, color), -1)

    return img

# Générer 50 fonds
for i in range(50):
    bg = generate_background()
    cv2.imwrite(os.path.join(out_dir, f"bg_{i:03d}.png"), bg)

print(f"✅ 50 fonds générés dans {out_dir}")

python ./OCR/text_renderer/main.py --corpus_file ./corpus_juridique_600k.txt --font_dir ./OCR/text_renderer/fonts --bg_dir ./OCR/text_renderer/backgrounds --num_img 100000 --save_dir ./OCR/text_renderer/paddleocr_synth --img_height 64 --img_width 256 --chars_file ./OCR/PADDLE_TRAINING/dict/latin_dict.txt