const v = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        canvas: v("canvas"),
        surface: v("surface"),
        raised: v("raised"),
        line: { DEFAULT: v("line"), strong: v("line-strong") },
        text: v("text"),
        muted: v("muted"),
        accent: { DEFAULT: v("accent"), hover: v("accent-hover"), fg: v("on-accent") },
        ok: v("ok"),
        warn: v("warn"),
        danger: v("danger"),
        info: v("info"),
        violet: v("violet"),
        orange: v("orange"),
        neutral: v("neutral"),
      },
      fontSize: {
        "2xs": ["11px", "14px"],
        xs: ["12px", "16px"],
        sm: ["13px", "18px"],
        base: ["13px", "18px"],
        md: ["15px", "20px"],
        lg: ["18px", "24px"],
        xl: ["22px", "28px"],
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      borderRadius: { DEFAULT: "6px", md: "6px", lg: "10px" },
      boxShadow: { dialog: "var(--shadow-dialog)" },
      maxWidth: { page: "1440px" },
    },
  },
  plugins: [],
};
