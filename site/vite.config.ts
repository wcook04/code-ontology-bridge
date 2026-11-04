import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { createReadStream, existsSync, statSync, writeFileSync } from "node:fs";
import { resolve, normalize, sep } from "node:path";

// The site reads the static publication from ./data/ beside its own index.html,
// exactly as GitHub Pages serves it. During development and preview that folder
// is served from a local staged deployment (COB_DATA_DIR, by default the
// ignored ../build/pages-release/data written by tools/stage_publication.py).
// The build never copies data into dist: the deployment keeps data/ separately.
function localData(dir: string): Plugin {
  const root = resolve(dir);
  const serve = (server: { middlewares: { use: (fn: (req: any, res: any, next: () => void) => void) => void } }) => {
    server.middlewares.use((req, res, next) => {
      const path = req.url?.split("?", 1)[0] ?? "";
      const match = path.match(/^\/data\/(.+)$/);
      if (!match) return next();
      const file = normalize(resolve(root, decodeURIComponent(match[1])));
      if (!file.startsWith(root + sep) || !existsSync(file) || !statSync(file).isFile()) {
        res.statusCode = 404;
        return res.end("Not in the local publication");
      }
      res.setHeader("Content-Type", "application/json");
      createReadStream(file).pipe(res);
    });
  };
  return {
    name: "local-publication-data",
    configureServer: serve,
    configurePreviewServer: serve,
    closeBundle() {
      writeFileSync(resolve("dist", ".nojekyll"), "");
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    base: env.VITE_BASE_PATH ?? "./",
    plugins: [react(), localData(env.COB_DATA_DIR ?? "../build/pages-release/data")],
    server: { port: 5181, strictPort: true },
    preview: { port: 4181, strictPort: true },
    build: { target: "es2022", sourcemap: false, emptyOutDir: true },
    test: { environment: "jsdom", include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"] },
  };
});
