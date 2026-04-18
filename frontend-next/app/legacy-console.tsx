import fs from "node:fs";
import path from "node:path";
import LegacyAppLoader from "./legacy-app-loader";

type LegacyConsoleProps = {
  wrapperClassName?: string;
  extraBootstrapScript?: string;
};

function loadLegacyFile(relativePath: string): string {
  const absolute = path.join(process.cwd(), "public", "legacy", relativePath);
  return fs.readFileSync(absolute, "utf8");
}

export default function LegacyConsole({
  wrapperClassName,
  extraBootstrapScript = "",
}: LegacyConsoleProps) {
  const markup = loadLegacyFile("brainscape-body.html");
  const importMap = loadLegacyFile("three-importmap.json");
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
  const apiBootstrap = `window.__BRAINGSCAPE_API_BASE__ = ${JSON.stringify(apiBase)}; window.__BRAINSCAPE_API_BASE__ = ${JSON.stringify(apiBase)};`;
  const bootstrapPayload = [apiBootstrap, extraBootstrapScript].filter(Boolean).join("\n");

  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: bootstrapPayload }} />
      <script type="importmap" dangerouslySetInnerHTML={{ __html: importMap }} />
      <div
        className={wrapperClassName}
        suppressHydrationWarning
        dangerouslySetInnerHTML={{ __html: markup }}
      />
      <LegacyAppLoader />
    </>
  );
}
