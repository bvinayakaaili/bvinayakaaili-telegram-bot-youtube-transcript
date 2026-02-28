/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'DM Sans'", "sans-serif"],
        display: ["'Syne'", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      colors: {
        surface: {
          0: "#0A0C0F",
          1: "#111318",
          2: "#191D24",
          3: "#1F242D",
          4: "#262C38",
        },
        accent: {
          DEFAULT: "#3B82F6",
          bright: "#60A5FA",
          dim: "#1D4ED8",
        },
        gold: {
          DEFAULT: "#F59E0B",
          bright: "#FCD34D",
          dim: "#B45309",
        },
        muted: "#4B5563",
        subtle: "#6B7280",
        soft: "#9CA3AF",
        text: "#E5E7EB",
        "text-bright": "#F9FAFB",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
      },
      animation: {
        "fade-in": "fadeIn 0.5s ease forwards",
        "slide-up": "slideUp 0.4s ease forwards",
        "pulse-slow": "pulse 3s ease-in-out infinite",
        shimmer: "shimmer 2s linear infinite",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: 0 }, "100%": { opacity: 1 } },
        slideUp: { "0%": { opacity: 0, transform: "translateY(12px)" }, "100%": { opacity: 1, transform: "translateY(0)" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
      },
    },
  },
  plugins: [],
}