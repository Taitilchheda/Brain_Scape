"use client";

import { useEffect } from "react";

export default function LegacyAppLoader() {
  useEffect(() => {
    const existing = document.querySelector('script[data-brainscape-legacy-app="true"]');
    if (existing) {
      return;
    }

    const script = document.createElement("script");
    script.type = "module";
    script.src = "/legacy/brainscape-app.js";
    script.dataset.brainscapeLegacyApp = "true";
    document.body.appendChild(script);
  }, []);

  return null;
}
