import { useEffect, useRef } from "react";
import type { KodaStateName } from "../types";

interface AcousticOrbProps {
  state: KodaStateName;
  size?: number;
}

const STATE_TOKEN: Record<KodaStateName, string> = {
  idle: "--accent-primary",
  listening: "--accent-cyan",
  thinking: "--accent-gold",
  shifting: "--accent-gold",
  speaking: "--accent-emerald",
  confirm_needed: "--accent-crimson"
};

export function AcousticOrb({ state, size = 34 }: AcousticOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext("2d");
    } catch {
      return;
    }
    if (!ctx) return;

    const reducedMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let rafId = 0;
    let phase = 0;

    const draw = () => {
      if (!ctx) return;
      const styles = getComputedStyle(document.documentElement);
      const color = styles.getPropertyValue(STATE_TOKEN[state]).trim() || "#3B82F6";

      ctx.clearRect(0, 0, size, size);
      const center = size / 2;
      const pulse = reducedMotion ? 0 : Math.sin(phase) * (state === "idle" ? 1.2 : 2.8);

      ctx.beginPath();
      ctx.arc(center, center, center - 4 + pulse * 0.4, 0, Math.PI * 2);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.6;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(center, center, Math.max(4, center * 0.36 + pulse * 0.25), 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      phase += state === "idle" ? 0.04 : 0.14;
      if (!reducedMotion) {
        rafId = requestAnimationFrame(draw);
      }
    };

    draw();
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [state, size]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      aria-label={`Koda Acoustic Core state ${state}`}
      style={{ display: "block", width: size, height: size }}
    />
  );
}
