"""Normalise ordinary property/cleaning photos, independently of guest ID policy."""
import io
import warnings
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)
FORMATS = {"JPEG", "PNG", "WEBP", "AVIF", "HEIF", "BMP", "TIFF", "GIF"}
PHOTO_ERROR = "Choose a valid JPG, PNG, WebP, AVIF, HEIC/HEIF, BMP, TIFF or GIF photo up to 50 megapixels."


def normalise_photo(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in FORMATS or source.width * source.height > 50_000_000:
                    raise HTTPException(422, PHOTO_ERROR)
                source.seek(0)  # Animated/multipage images use the first frame only.
                source.draft("RGB", (2400, 2400))
                source.thumbnail((2400, 2400))
                image = ImageOps.exif_transpose(source)
                rgba = image.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                output = io.BytesIO()
                clean.save(output, "JPEG", quality=85, optimize=True)
                return output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, PHOTO_ERROR) from exc
