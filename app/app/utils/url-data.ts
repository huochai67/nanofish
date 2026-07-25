export type ParsedUrlData<T> =
  | { data: T; error: null }
  | { data: null; error: string };
const MAX_URL_DATA_LENGTH = 200_000;

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

export function encodeUrlData(value: unknown): string {
  const encoded = bytesToBase64(new TextEncoder().encode(JSON.stringify(value)));
  if (encoded.length > MAX_URL_DATA_LENGTH) {
    throw new RangeError("URL data exceeds the sharing limit.");
  }
  return encoded;
}

export function parseUrlData<T>(
  value: string,
  validate: (data: unknown) => T | null,
): ParsedUrlData<T> {
  if (value.length > MAX_URL_DATA_LENGTH) {
    return { data: null, error: "URL data exceeds the sharing limit." };
  }

  try {
    const json = new TextDecoder().decode(base64ToBytes(value));
    const data = validate(JSON.parse(json));
    return data
      ? { data, error: null }
      : { data: null, error: "URL data has an unsupported structure." };
  } catch {
    return { data: null, error: "URL data could not be decoded." };
  }
}
