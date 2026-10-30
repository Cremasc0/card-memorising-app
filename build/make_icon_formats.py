from pathlib import Path
import struct
from PIL import Image

root = Path(__file__).resolve().parent
image = Image.open(root / 'card-drill-icon.png').convert('RGBA')
image.save(root / 'card-drill-icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])

chunks = []
for size, chunk_type in [(16,'icp4'),(32,'icp5'),(64,'icp6'),(128,'ic07'),(256,'ic08'),(512,'ic09'),(1024,'ic10')]:
    png_path = root / f'.icon-{size}.png'
    image.resize((size,size), Image.Resampling.LANCZOS).save(png_path, format='PNG', optimize=True)
    payload = png_path.read_bytes()
    png_path.unlink()
    chunks.append(chunk_type.encode('ascii') + struct.pack('>I', len(payload) + 8) + payload)
body = b''.join(chunks)
(root / 'card-drill-icon.icns').write_bytes(b'icns' + struct.pack('>I', len(body) + 8) + body)
