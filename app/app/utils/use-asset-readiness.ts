"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const ASSET_TIMEOUT_MS = 10_000;

export function useAssetReadiness() {
  const [ready, setReady] = useState(false);
  const pendingAssets = useRef(0);
  const timeout = useRef<number | null>(null);

  const clearTimeout = useCallback(() => {
    if (timeout.current !== null) {
      window.clearTimeout(timeout.current);
      timeout.current = null;
    }
  }, []);

  const completeAsset = useCallback(() => {
    if (pendingAssets.current <= 0) return;

    pendingAssets.current -= 1;
    if (pendingAssets.current === 0) {
      clearTimeout();
      setReady(true);
    }
  }, [clearTimeout]);

  const beginAssetTracking = useCallback(
    (count: number) => {
      clearTimeout();
      pendingAssets.current = count;
      setReady(count === 0);

      if (count > 0) {
        timeout.current = window.setTimeout(() => {
          pendingAssets.current = 0;
          setReady(true);
        }, ASSET_TIMEOUT_MS);
      }
    },
    [clearTimeout],
  );

  useEffect(() => clearTimeout, [clearTimeout]);

  return { ready, beginAssetTracking, completeAsset };
}
