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
  return typeof field === "string" ? field : undefined;
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
