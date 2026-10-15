/**
 * Get a chosen photo ready to be a profile picture, in the browser: rotated the right way up,
 * cropped to a centred square and shrunk to at most 512 px, as a JPEG. That keeps the upload
 * to about 100 KB, and lets phones' HEIC photos through on browsers that can open them. The
 * API checks and re-encodes it again (serve_api/avatars.py).
 */
export const AVATAR_SIZE = 512;
const MIN_SIDE = 64;
const MAX_FILE_BYTES = 25 * 1024 * 1024;

export class AvatarFileError extends Error {}

export async function prepareAvatar(file: File, size = AVATAR_SIZE): Promise<Blob> {
  if (file.type && !file.type.startsWith("image/")) throw new AvatarFileError("Choose a picture: a JPEG, PNG or WebP.");
  if (file.size > MAX_FILE_BYTES) throw new AvatarFileError("That picture is over 25 MB. Choose a smaller one.");
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new AvatarFileError("We couldn't open that picture. Try a JPEG or PNG.");
  }
  const side = Math.min(bitmap.width, bitmap.height);
  if (side < MIN_SIDE) {
    bitmap.close();
    throw new AvatarFileError(`That picture is too small. It needs to be at least ${MIN_SIDE} pixels wide.`);
  }
  const out = Math.min(size, side);
  const canvas = document.createElement("canvas");
  canvas.width = out;
  canvas.height = out;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new AvatarFileError("Your browser couldn't prepare the picture.");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, out, out);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob) throw new AvatarFileError("Your browser couldn't prepare the picture.");
  return blob;
}
