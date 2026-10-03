import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "node:path";

// One HTML entry per poster box, so each iframe loads only its own code.
// The build goes to docs/, which GitHub Pages serves from this branch.
export default defineConfig({
  base: "/iac-project/",
  plugins: [vue()],
  build: {
    outDir: "docs",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        home: resolve(import.meta.dirname, "index.html"),
        box1: resolve(import.meta.dirname, "box1/index.html"),
      },
    },
  },
});
