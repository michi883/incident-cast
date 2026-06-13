import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      // Operational interface, not a SaaS dashboard: corners are nearly square. Overriding the
      // scale (not extending) sharpens every existing rounded-* utility app-wide at once.
      borderRadius: {
        none: "0px",
        sm: "2px",
        DEFAULT: "2px",
        md: "3px",
        lg: "3px",
        xl: "4px",
        "2xl": "6px",
        "3xl": "8px",
        full: "9999px",
      },
      colors: {
        ink: {
          50: "#f5f6f8",
          100: "#e7e8ee",
          200: "#cdcfd9",
          300: "#a6a9b8",
          400: "#787c8d",
          500: "#565b6b",
          600: "#3b3f4c",
          700: "#2a2d38",
          800: "#181a22",
          900: "#0d0e14",
          950: "#070809",
        },
        specialist: {
          reliability: "#d97706",
          deployment: "#0ea5e9",
          access: "#a855f7",
          blast_radius: "#10b981",
        },
        severity: {
          info: "#64748b",
          notable: "#d97706",
          critical: "#dc2626",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
