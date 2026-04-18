import type { Metadata } from "next";
import LegacyConsole from "../../legacy-console";
import styles from "./fullscreen.module.css";

export const metadata: Metadata = {
  title: "Brain Scape Precision Viewer",
  description: "Fullscreen high-precision 3D viewer for clinical review",
};

export default function PrecisionViewerPage() {
  return <LegacyConsole wrapperClassName={styles.fullscreenWrapper} />;
}
