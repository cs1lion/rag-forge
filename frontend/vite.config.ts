import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 后端 FastAPI 运行在 8000；开发期经代理避免跨域。
// BACKEND_ORIGIN 可在端口冲突/多实例并行时覆盖代理目标（默认 8000）。
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.FRONTEND_PORT ?? 5173),
    proxy: {
      "/api": { target: process.env.BACKEND_ORIGIN ?? "http://localhost:8000", changeOrigin: true },
    },
  },
});
