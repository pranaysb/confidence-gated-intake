import "./globals.css";

export const metadata = {
  title: "Confidence-Gated Intake — Dashboard",
  description: "Extraction accuracy and confidence, measured, not asserted.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
