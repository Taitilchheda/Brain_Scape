import fs from "node:fs";
import path from "node:path";

function loadLegacyFile(relativePath: string): string {
  const absolute = path.join(process.cwd(), "public", "legacy", relativePath);
  return fs.readFileSync(absolute, "utf8");
}

export default function HomePage() {
  const markup = loadLegacyFile("brainscape-body.html");
  const importMap = loadLegacyFile("three-importmap.json");
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
  const apiBootstrap = `window.__BRAINGSCAPE_API_BASE__ = ${JSON.stringify(apiBase)}; window.__BRAINSCAPE_API_BASE__ = ${JSON.stringify(apiBase)};`;

  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: apiBootstrap }} />
      <script type="importmap" dangerouslySetInnerHTML={{ __html: importMap }} />
      <div dangerouslySetInnerHTML={{ __html: markup }} />
      <script type="module" src="/legacy/brainscape-app.js" />
    </>
  );
}
