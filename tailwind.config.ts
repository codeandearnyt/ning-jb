import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        panel2: "rgb(var(--panel2) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        heat: "rgb(var(--heat) / <alpha-value>)",
        hot: "rgb(var(--hot) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        good: "rgb(var(--good) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        none: "0",
        sm: "6px",
        DEFAULT: "8px",
        md: "10px",
        lg: "14px",
      },
      boxShadow: {
        card: "0 1px 2px rgb(26 16 22 / 0.04), 0 18px 40px -24px rgb(190 24 93 / 0.28)",
      },
      keyframes: {
        forgeIn: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        heatSweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        pulseDot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        forgeIn: "forgeIn 260ms cubic-bezier(0.16, 1, 0.3, 1) both",
        heatSweep: "heatSweep 1.4s linear infinite",
        pulseDot: "pulseDot 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
