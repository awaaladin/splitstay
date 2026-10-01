/**
 * SplitStay design tokens.
 *
 * `theme.colors` is set (not `extend`ed), so Tailwind's default blue/gray/etc. do not exist here.
 * Two brand colours only: deep navy and white. Everything else is either a neutral charcoal ramp
 * or a semantic token that flips between light and dark through CSS variables (see input.css).
 */
const semantic = (name) => `rgb(var(--${name}) / <alpha-value>)`;

module.exports = {
  darkMode: "class",
  content: ["./templates/**/*.html", "./apps/**/*.py", "./static/js/**/*.js"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "#ffffff",
      navy: {
        50: "#eef2f9",
        100: "#dbe4f3",
        200: "#b9c8e6",
        300: "#8fa5d2",
        400: "#5f83c4",
        500: "#3e63a8",
        600: "#2b4a83",
        700: "#1f3a6c",
        800: "#172d57",
        900: "#102a56",
        950: "#0a1630",
      },
      // Charcoal ramp: body text is ink-800, never pure black.
      ink: {
        50: "#f6f7f9",
        100: "#eceef2",
        200: "#d8dce3",
        300: "#b6bdca",
        400: "#8a93a5",
        500: "#667085",
        600: "#4b5468",
        700: "#383f50",
        800: "#2a2f3d",
        900: "#1f2330",
      },
      // Semantic tokens, resolved per theme.
      canvas: semantic("canvas"),
      surface: semantic("surface"),
      sunken: semantic("sunken"),
      line: semantic("line"),
      "line-strong": semantic("line-strong"),
      fg: semantic("body"),
      muted: semantic("muted"),
      primary: semantic("primary"),
      "primary-hover": semantic("primary-hover"),
      "on-primary": semantic("on-primary"),
      "primary-soft": semantic("primary-soft"),
      ok: semantic("ok"),
      "ok-soft": semantic("ok-soft"),
      warn: semantic("warn"),
      "warn-soft": semantic("warn-soft"),
      danger: semantic("danger"),
      "danger-soft": semantic("danger-soft"),
    },
    fontFamily: {
      sans: ['"Inter"', "ui-sans-serif", "system-ui", "-apple-system", '"Segoe UI"', "Roboto", "sans-serif"],
    },
    // A real type scale: each step differs in size, weight and tracking, not just size.
    fontSize: {
      micro: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.08em", fontWeight: "600" }],
      meta: ["0.8125rem", { lineHeight: "1.25rem" }],
      body: ["0.9375rem", { lineHeight: "1.5rem" }],
      lead: ["1.0625rem", { lineHeight: "1.65rem" }],
      section: ["1.125rem", { lineHeight: "1.5rem", letterSpacing: "-0.005em", fontWeight: "600" }],
      title: ["1.625rem", { lineHeight: "2rem", letterSpacing: "-0.015em", fontWeight: "650" }],
      display: ["2.5rem", { lineHeight: "2.75rem", letterSpacing: "-0.025em", fontWeight: "650" }],
      figure: ["2.125rem", { lineHeight: "2.5rem", letterSpacing: "-0.02em", fontWeight: "600" }],
    },
    extend: {
      borderRadius: { DEFAULT: "6px", md: "8px", lg: "10px", xl: "14px" },
      boxShadow: {
        card: "0 1px 0 rgb(var(--line) / 0.6), 0 1px 2px rgb(16 42 86 / 0.04)",
        raised: "0 8px 30px -12px rgb(10 22 48 / 0.28)",
      },
      transitionTimingFunction: {
        // Slightly springy settle, used for state changes that should feel physical.
        settle: "cubic-bezier(0.34, 1.3, 0.5, 1)",
        calm: "cubic-bezier(0.22, 0.7, 0.2, 1)",
      },
      maxWidth: { page: "72rem" },
    },
  },
  plugins: [],
};
