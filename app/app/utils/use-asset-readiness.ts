"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const ASSET_TIMEOUT_MS = 10_000;
export type AssetReadiness = "pending" | "ready" | "timeout";

export function useAssetReadiness() {
  const [status, setStatus] = useState<AssetReadiness>("pending");
  const pendingAssets = useRef(0);
  const timeout = useRef<number | null>(null);
  const fontsReady = useRef(false);
  const timedOut = useRef(false);

  const clearTimeout = useCallback(() => {
    if (timeout.current !== null) {
      window.clearTimeout(timeout.current);
      timeout.current = null;
    }
  }, []);

  const markReadyIfComplete = useCallback(() => {
    if (!timedOut.current && fontsReady.current && pendingAssets.current === 0) {
      setStatus("ready");
    }
  }, []);

  const completeAsset = useCallback(() => {
    if (timedOut.current || pendingAssets.current <= 0) return;

    pendingAssets.current -= 1;
    if (pendingAssets.current === 0) {
      clearTimeout();
      markReadyIfComplete();
    }
  }, [clearTimeout, markReadyIfComplete]);

  const beginAssetTracking = useCallback(
    (count: number) => {
      clearTimeout();
      pendingAssets.current = count;
      timedOut.current = false;
      setStatus("pending");

      if (count > 0) {
        timeout.current = window.setTimeout(() => {
          timedOut.current = true;
          setStatus("timeout");
        }, ASSET_TIMEOUT_MS);
      } else {
        markReadyIfComplete();
      }
    },
    [clearTimeout, markReadyIfComplete],
  );

  useEffect(() => {
    void document.fonts.ready.then(() => {
      fontsReady.current = true;
      markReadyIfComplete();
    });

    return clearTimeout;
  }, [clearTimeout, markReadyIfComplete]);

  return { status, beginAssetTracking, completeAsset };
}
