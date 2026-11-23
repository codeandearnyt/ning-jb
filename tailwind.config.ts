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
        /* Pink ramp. Surfaces first, then strokes. Text never sits on 400+. */
        pink: {
          50: "rgb(var(--pink-50) / <alpha-value>)",
          100: "rgb(var(--pink-100) / <alpha-value>)",
          200: "rgb(var(--pink-200) / <alpha-value>)",
          300: "rgb(var(--pink-300) / <alpha-value>)",
          400: "rgb(var(--pink-400) / <alpha-value>)",
          500: "rgb(var(--pink-500) / <alpha-value>)",
          600: "rgb(var(--pink-600) / <alpha-value>)",
          700: "rgb(var(--pink-700) / <alpha-value>)",
          800: "rgb(var(--pink-800) / <alpha-value>)",
        },
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
        lift: "0 2px 4px rgb(26 16 22 / 0.05), 0 26px 52px -28px rgb(190 24 93 / 0.42)",
        heat: "0 12px 28px -12px rgb(190 24 93 / 0.75)",
      },
      /* The one curve and the three durations. Everything else is a mistake. */
      transitionTimingFunction: {
        forge: "cubic-bezier(0.16, 1, 0.3, 1)",
        exit: "cubic-bezier(0.4, 0, 1, 1)",
      },
      transitionDuration: {
        160: "160ms",
        240: "240ms",
        420: "420ms",
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
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.4", transform: "scale(0.82)" },
        },
        drift: {
          "0%, 100%": { transform: "translate3d(0, 0, 0) scale(1)" },
          "50%": { transform: "translate3d(-24px, 18px, 0) scale(1.06)" },
        },
        rise: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        forgeIn: "forgeIn 260ms cubic-bezier(0.16, 1, 0.3, 1) both",
        heatSweep: "heatSweep 1.4s linear infinite",
        pulseDot: "pulseDot 2.4s ease-in-out infinite",
        drift: "drift 18s ease-in-out infinite alternate",
        rise: "rise 420ms cubic-bezier(0.16, 1, 0.3, 1) both",
      },
    },
  },
  plugins: [],
};

export default config;
