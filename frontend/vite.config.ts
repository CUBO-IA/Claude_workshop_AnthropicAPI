import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    https: true,
    proxy: {
      "/api": {
        target: "https://127.0.0.1:8453",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
