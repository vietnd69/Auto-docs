import zlib
import base64

def encode_content(content_str: str) -> str:
    compressed = zlib.compress(content_str.encode("utf-8"))
    return base64.b64encode(compressed).decode("ascii")

def decode_content(content_z: str) -> str:
    compressed = base64.b64decode(content_z)
    return zlib.decompress(compressed).decode("utf-8")

c1 = "hello world\n"
c1_z = encode_content(c1)
print(f"{c1!r} -> {c1_z}")
print(f"decoded: {decode_content(c1_z)!r}")
