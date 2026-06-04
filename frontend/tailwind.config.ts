import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        library: {
          ink: "#20232d",
          muted: "#667085",
          green: "#0c6b4f",
          teal: "#0f8a7a",
          mint: "#e7f6f1",
          purple: "#98298f",
          plum: "#6f1e67",
          blue: "#d7e8ff",
          gold: "#b88a2e",
          line: "#e5e7ef",
          paper: "#f7f8fb",
          surface: "#ffffff"
        }
      },
      boxShadow: {
        ledger: "0 18px 42px rgba(32, 35, 45, 0.08)",
        soft: "0 10px 30px rgba(32, 35, 45, 0.07)"
      }
    }
  },
  plugins: []
};

export default config;
