import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Moot Court Memorial Toolkit",
  description: "Check a moot court memorial against your competition's rules before you submit.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <header className="border-b border-line bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="h-serif text-lg font-semibold text-brand">
              Moot Court Memorial Toolkit
            </Link>
            <nav className="text-sm font-medium">
              <Link href="/projects" className="rounded-md px-3 py-1.5 hover:bg-slate-100">
                Projects
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-line py-4 text-center text-xs text-slate-500">
          Automated checks support your final review. They do not replace it.
        </footer>
      </body>
    </html>
  );
}
