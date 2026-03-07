import os
from PIL import Image


def crop_to_square(image_path: str) -> str:
    """Recorta una imagen a cuadrado centrado y la guarda como PNG. Devuelve la ruta del PNG."""
    with Image.open(image_path) as img:
        min_dim = min(img.size)
        left = (img.width - min_dim) / 2
        top = (img.height - min_dim) / 2
        right = (img.width + min_dim) / 2
        bottom = (img.height + min_dim) / 2
        img = img.crop((left, top, right, bottom))

        png_path = os.path.splitext(image_path)[0] + ".png"
        img.save(png_path, "PNG")
        return png_path


def process_thumbnails(thumbnails_dir: str) -> None:
    """Recorta a cuadrado todas las thumbnails del directorio."""
    for file in os.listdir(thumbnails_dir):
        path = os.path.join(thumbnails_dir, file)
        ext = os.path.splitext(file)[1].lower()
        if ext in (".jpg", ".jpeg", ".webp", ".png"):
            crop_to_square(path)
