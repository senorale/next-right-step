import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { GoogleAnalytics } from '@next/third-parties/google'
import SideNav from "./components/nav/SideNav";
import Footer from "./components/nav/Footer";
import FeedbackDialog from "./components/FeedbackDialog";

const inter = Inter({ subsets: ["latin"] });

const description = "A free financial tool to help you take your next right step: compare the real cost and payoff of college, trades, and careers.";

export const metadata: Metadata = {
  // Link previews need absolute image URLs. SITE_URL overrides the default, e.g. for a custom domain.
  metadataBase: new URL(process.env.SITE_URL ?? "https://next-right-step.up.railway.app"),
  title: "Next Right Step",
  description,
  openGraph: { title: "Next Right Step", description, siteName: "Next Right Step", type: "website" },
  twitter: { card: "summary_large_image", title: "Next Right Step", description },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="flex min-h-screen flex-col">
          <div className="flex flex-1">
            <SideNav />
            <div className="min-w-0 flex-1">{children}</div>

          </div>
          <Footer />
          <FeedbackDialog />
        </div>
      </body>
      <GoogleAnalytics gaId={process.env.NEXT_PUBLIC_GA_ID!} />
    </html>
  );
}
