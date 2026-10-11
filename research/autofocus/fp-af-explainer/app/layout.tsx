import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SIGMA fp 自動對焦設計解剖",
  description: "從韌體證據理解 SIGMA fp 對比式自動對焦的流程、設計理由與工程權衡。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-Hant"><body>{children}</body></html>;
}
