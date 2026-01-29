import os
import uuid
import io
import base64
import qrcode
from PIL import Image, ImageColor
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer, GappedSquareModuleDrawer,
    CircleModuleDrawer, RoundedModuleDrawer
)
from qrcode.image.styles.colormasks import SolidFillColorMask
from flask import current_app

def generate_styled_qr(short_code, color_dark="#000000", style="square", logo_data=None, logo_path=None):
    """
    Generates a styled QR code for the given short_code.
    Returns the relative static path to the generated QR image.
    """
    base_url = current_app.config.get("BASE_URL", "http://127.0.0.1:5000")
    qr_data = f"{base_url}/{short_code}?source=qr"

    qr_dir = os.path.join(current_app.static_folder or "static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)

    qr_filename = f"qr_{uuid.uuid4().hex}.png"
    qr_path = os.path.join(qr_dir, qr_filename)

    # 1. Color
    try:
        fill_rgb = ImageColor.getrgb(color_dark)
    except:
        fill_rgb = (0, 0, 0)
    back_rgb = (255, 255, 255)

    # 2. Style (Drawer)
    style = style.lower()
    drawer_map = {
        "square": SquareModuleDrawer(),
        "dots": GappedSquareModuleDrawer(),
        "circle": CircleModuleDrawer(),
        "rounded": RoundedModuleDrawer(),
        "vertical-bars": GappedSquareModuleDrawer(),
        "horizontal-bars": GappedSquareModuleDrawer(),
        "mosaic": CircleModuleDrawer(),
        "beads": RoundedModuleDrawer(),
    }
    drawer = drawer_map.get(style, SquareModuleDrawer())

    # 3. Generate QR Object
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    # 4. Create Image
    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        color_mask=SolidFillColorMask(back_color=back_rgb, front_color=fill_rgb)
    ).convert("RGB")

    # 5. Logo Overlay
    logo_img = None
    if logo_data:
        try:
            if "," in logo_data:
                logo_data = logo_data.split(",", 1)[1]
            logo_bytes = base64.b64decode(logo_data)
            logo_img = Image.open(io.BytesIO(logo_bytes))
        except Exception as e:
            current_app.logger.warning(f"Logo data embedding failed: {e}")
            
    elif logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path)
        except Exception as e:
            current_app.logger.warning(f"Logo file embedding failed: {e}")

    if logo_img:
        try:
            qr_w, qr_h = qr_img.size
            size = int(qr_w * 0.25)
            logo_img = logo_img.resize((size, size))

            pos = ((qr_w - size) // 2, (qr_h - size) // 2)
            # Handle RGBA logos
            if logo_img.mode == 'RGBA':
                qr_img.paste(logo_img, pos, logo_img)
            else:
                qr_img.paste(logo_img, pos)
        except Exception as e:
            current_app.logger.warning(f"Logo paste failed: {e}")

    # 6. Save
    qr_img.save(qr_path)
    static_rel = os.path.relpath(qr_path, start=current_app.static_folder or "static").replace("\\", "/")
    
    return static_rel
