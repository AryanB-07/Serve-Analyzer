"""Profile pictures: checked and stripped of metadata before they're stored, without decoding.

The browser decodes the chosen photo, crops it to a centred square, shrinks it to 512 px and
re-encodes it as a JPEG (frontend/src/lib/avatar.ts). Re-encoding drops everything phones put in
photos, including the GPS position. The API doesn't load an image library, keeping its process
small (tests/test_footprint.py). Instead it checks the JPEG's structure:
- a square of 64 to 1024 px, read from the frame header;
- complete, ending with the end-of-image marker;
- at most 1 MB, the proxy's limit for everything but videos.
It then removes any metadata segments (EXIF, XMP, ICC, IPTC, comments), for clients that send a
photo straight from a camera. It's served back as image/jpeg with nosniff, so a file that isn't
really an image can't be run as anything else.
"""

from __future__ import annotations

MAX_BYTES = 1024 * 1024
MAX_SIDE = 1024
MIN_SIDE = 64

SOI, EOI, SOS = 0xD8, 0xD9, 0xDA
# Start-of-frame markers carry the image size (every SOFn except DHT, JPG and DAC).
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
# What a decoder needs before the image data: quantisation and Huffman tables, the frame
# header, restart interval, and JFIF's APP0 (density). Everything else (APP1-APP15, comments)
# is metadata.
_KEEP = _SOF | {0xC4, 0xDB, 0xDD, 0xE0}


class AvatarError(ValueError):
    """A picture that can't be used; the message is for the person."""


def _segments(data: bytes):
    """(marker, start, end) of each segment before the image data, then (SOS, start, len(data))."""
    if not data.startswith(b"\xff\xd8"):
        raise AvatarError("That doesn't look like a JPEG picture.")
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise AvatarError("That picture couldn't be read.")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == SOS:
            yield marker, i, len(data)
            return
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if length < 2 or i + 2 + length > len(data):
            raise AvatarError("That picture couldn't be read.")
        yield marker, i, i + 2 + length
        i += 2 + length
    raise AvatarError("That picture couldn't be read.")


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a JPEG's frame header, or None if it has none."""
    try:
        for marker, start, end in _segments(data):
            if marker in _SOF and end - start >= 9:
                return (int.from_bytes(data[start + 7:start + 9], "big"),
                        int.from_bytes(data[start + 5:start + 7], "big"))
    except AvatarError:
        return None
    return None


def clean(data: bytes) -> bytes:
    """The JPEG with its metadata removed, if it's one we can use as a profile picture."""
    if len(data) > MAX_BYTES:
        raise AvatarError("Pictures must be under 1 MB.")
    kept, size = [b"\xff\xd8"], None
    for marker, start, end in _segments(data):
        if marker in _SOF:
            size = (int.from_bytes(data[start + 7:start + 9], "big"), int.from_bytes(data[start + 5:start + 7], "big"))
        if marker == SOS:
            kept.append(data[start:end])  # the image data, to the end of the file
        elif marker in _KEEP and not (marker == 0xE0 and data[start + 4:start + 9] != b"JFIF\x00"):
            kept.append(data[start:end])
    if size is None:
        raise AvatarError("That picture couldn't be read.")
    if not data.rstrip(b"\x00").endswith(b"\xff\xd9"):
        raise AvatarError("That picture is incomplete. Try choosing it again.")
    width, height = size
    if width != height:
        raise AvatarError("Pictures need to be square.")
    if width > MAX_SIDE:
        raise AvatarError(f"Pictures can be up to {MAX_SIDE} pixels wide.")
    if width < MIN_SIDE:
        raise AvatarError(f"Pictures need to be at least {MIN_SIDE} pixels wide.")
    return b"".join(kept)
