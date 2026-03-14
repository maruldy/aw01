/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f3ede2",
        ink: "#1c1b19",
        signal: "#c45b32",
        ocean: "#0f5c63",
        sand: "#e6d3ba",
        pine: "#274338"
      },
      boxShadow: {
        panel: "0 24px 60px rgba(28, 27, 25, 0.12)"
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'IBM Plex Sans'", "sans-serif"]
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: 0, transform: "translateY(12px)" },
          "100%": { opacity: 1, transform: "translateY(0)" }
        }
      },
      animation: {
        "fade-up": "fade-up 420ms ease-out"
      }
    }
  },
  plugins: []
};
