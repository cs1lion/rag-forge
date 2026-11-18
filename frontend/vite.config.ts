import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 后端 FastAPI 运行在 8000；开发期经代理避免跨域。
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.FRONTEND_PORT ?? 5173),
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
