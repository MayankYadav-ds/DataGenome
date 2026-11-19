import type { Metadata } from "next";
import "./globals.css";
import Providers from "../components/Providers";
export const metadata: Metadata = {
  metadataBase: new URL("http://127.0.0.1:3000"),
  title: {
    default: "DataGenome — Debug the data",
    template: "%s · DataGenome",
  },
  description:
    "Evidence-driven dataset debugging. Investigate labels, leakage and model failures locally.",
  icons: { icon: "/icon.svg" },
  openGraph: {
    title: "DataGenome — Debug the data, not just the model.",
    description: "A local-first dataset investigation workspace.",
    images: ["/social.png"],
  },
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
