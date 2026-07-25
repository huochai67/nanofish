export function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function optionalString(
  value: Record<string, unknown>,
  key: string,
): string | undefined {
  const field = value[key];
  return typeof field === "string" && field.length <= 20_000 ? field : undefined;
}

export function optionalSafeUrl(
  value: Record<string, unknown>,
  key: string,
  allowDataImage = false,
): string | null | undefined {
  const field = value[key];
  if (field === undefined) return undefined;
  if (typeof field !== "string" || field.length > 4_096) return null;
  if (field === "") return undefined;

  if (allowDataImage && field.startsWith("data:image/")) {
    return field.length <= 2_000_000 && /^data:image\/(png|jpeg|gif|webp);base64,[a-z0-9+/=\s]+$/i.test(field)
      ? field
      : null;
  }

  try {
    return new URL(field).protocol === "https:" ? field : null;
  } catch {
    return null;
  }
}

export function optionalNullableString(
  value: Record<string, unknown>,
  key: string,
): string | null | undefined {
  const field = value[key];
  return field === null || typeof field === "string" ? field : undefined;
}

export function optionalNullableNumber(
  value: Record<string, unknown>,
  key: string,
): number | null | undefined {
  const field = value[key];
  return field === null || (typeof field === "number" && Number.isFinite(field))
    ? field
    : undefined;
}
