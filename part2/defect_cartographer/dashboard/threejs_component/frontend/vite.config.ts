import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "build",
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: {
      entry: "./src/index.tsx",
      formats: ["es"],
      fileName: "index",
    },
    rollupOptions: {
      output: {
        entryFileNames: "index-[hash].js",
        assetFileNames: "style-[hash][extname]",
      },
    },
  },
});
