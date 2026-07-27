import type { CSSProperties, ReactNode } from "react";
import clsx from "clsx";
import { AlertCircle } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import type { AssetReadiness } from "../utils/use-asset-readiness";

/**
 * Shared page chrome. Every screenshot page renders at a 720px reference
 * width and scales down to mobile portrait; keep shells consistent.
 */

export function PageShell({
  ready,
  children,
  className,
  style,
}: {
  ready: AssetReadiness;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      data-ready={ready}
      style={style}
      className={clsx("min-h-screen bg-paper text-zinc-900", className)}
    >
      {children}
    </div>
  );
}

export function Content({
  children,
  className,
  flush = false,
}: {
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <div className={clsx("mx-auto w-full max-w-[720px]", !flush && "px-4 sm:px-5", className)}>
      {children}
    </div>
  );
}

export function PageHeader({
  icon,
  accent,
  title,
  subtitle,
  action,
}: {
  icon: ReactNode;
  /** Chip classes carrying the page accent, e.g. "bg-indigo-600 shadow-indigo-600/25". */
  accent: string;
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="border-b border-black/[0.06] bg-white">
      <Content className="flex items-center gap-3 py-3.5">
        <div
          className={clsx(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white shadow-sm",
            accent,
          )}
        >
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[15px] font-semibold tracking-tight text-zinc-900 sm:text-base">
            {title}
          </h1>
          {subtitle ? (
            <p className="truncate text-xs text-zinc-500">{subtitle}</p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </Content>
    </header>
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "rounded-2xl border border-black/[0.06] bg-white shadow-card",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-amber-200/80 bg-amber-50 px-3.5 py-3 text-sm leading-6 text-amber-900">
      <AlertCircle size={16} className="mt-1 shrink-0 text-amber-500" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/** Side rail with a QR code; hidden on narrow portrait layouts. */
export function QrRail({ url, size = 92 }: { url: string; size?: number }) {
  return (
    <div className="hidden w-[108px] shrink-0 flex-col items-center justify-center gap-1.5 self-stretch border-l border-black/[0.06] pl-4 sm:flex">
      <div className="rounded-lg border border-black/[0.06] bg-white p-1.5">
        <QRCodeSVG
          value={url}
          size={size}
          level="M"
          marginSize={1}
          bgColor="#ffffff"
          fgColor="#18181b"
        />
      </div>
      <span className="text-[10px] text-zinc-400">扫码打开</span>
    </div>
  );
}
