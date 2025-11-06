import cv2
import numpy as np
from PIL import Image

# --- Settings ---
src_path = "banner-alt.png"
dst_path = "car_lights_fadein_1080p_60fps.mp4"
W, H = 1920, 1080
fps = 60                # use 60 for broad compatibility
duration = 2            # seconds
num_frames = int(fps * duration)
bg_color = (0, 0, 0)    # background behind transparency (RGB)

# --- Load + alpha composite onto solid bg, then high-quality resize ---
img = Image.open(src_path).convert("RGBA")

# Alpha composite (gamma-aware composite is overkill here; this is fine for UI banners)
bg = Image.new("RGBA", img.size, bg_color + (255,))
img_rgba = Image.alpha_composite(bg, img)
img_rgb = img_rgba.convert("RGB")

# High-quality resize
img_rgb = img_rgb.resize((W, H), resample=Image.LANCZOS)

# To numpy, 0..1 sRGB
arr_srgb = np.asarray(img_rgb, dtype=np.float32) / 255.0

# --- sRGB <-> Linear helpers (for gamma-correct brightness) ---
def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)

def linear_to_srgb(x):
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * (x ** (1/2.4)) - 0.055)

arr_lin = srgb_to_linear(arr_srgb)

# --- Generate frames with a smooth ease-in curve ---
# Your curve is good; here’s an equivalent ease-in: sin^2(pi/2 * t)
frames = []
for i in range(num_frames):
    t = i / (num_frames - 1 if num_frames > 1 else 1)
    brightness = np.sin(0.5 * np.pi * t) ** 2
    frame_lin = np.clip(arr_lin * brightness, 0.0, 1.0)
    frame_srgb = np.clip(linear_to_srgb(frame_lin), 0.0, 1.0)
    frame_u8 = (frame_srgb * 255.0 + 0.5).astype(np.uint8)
    # OpenCV expects BGR
    frame_bgr = cv2.cvtColor(frame_u8, cv2.COLOR_RGB2BGR)
    frames.append(frame_bgr)

# --- Write video (prefer H.264 for compatibility) ---
# Try 'avc1' (H.264). If your OpenCV build lacks H.264, fall back to 'mp4v'.
fourcc = cv2.VideoWriter_fourcc(*'avc1')
out = cv2.VideoWriter(dst_path, fourcc, fps, (W, H))
if not out.isOpened():
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(dst_path, fourcc, fps, (W, H))

for f in frames:
    out.write(f)
out.release()
print(f"✅ Video saved as {dst_path}, {fps} fps, {W}x{H}")
