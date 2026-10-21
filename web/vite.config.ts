import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Hash routing + relative base: works on Vercel, GitHub Pages, or any static host.
export default defineConfig({
  base: "./",
  plugins: [react()],
});
