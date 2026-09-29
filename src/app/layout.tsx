import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { GoogleAnalytics } from '@next/third-parties/google'
import SideNav from "./components/nav/SideNav";
import Footer from "./components/nav/Footer";
import FeedbackDialog from "./components/FeedbackDialog";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Next Right Step",
  description: "Compare the real cost and payoff of college, trades, and careers",
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
