from pathlib import Path
import binascii
import struct
import zlib

root=Path(__file__).resolve().parents[1]
size=256
raw=bytearray()
heights=[48,86,132,176,114,66]
for y in range(size):
    raw.append(0)
    for x in range(size):
        inside=(abs(x-127.5)/124)**4+(abs(y-127.5)/124)**4<=1
        pixel=(17,155,134,255) if inside else (0,0,0,0)
        for i,height in enumerate(heights):
            cx=63+i*26
            if abs(x-cx)<=6 and abs(y-128)<=height/2:
                pixel=(255,255,255,255)
        raw.extend(pixel)
def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
assets=root/'assets';assets.mkdir(exist_ok=True)
(assets/'icon.png').write_bytes(png)
ico=struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',0,0,0,0,1,32,len(png),22)+png
(assets/'app.ico').write_bytes(ico)
(root/'electron'/'icon.png').write_bytes(png)
print('Original application icon created.')
