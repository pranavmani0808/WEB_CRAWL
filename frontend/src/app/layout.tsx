import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Popz AI Crawl',
  description: 'Sitemap-based website auditing and crawler dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full bg-slate-900 text-slate-100">
      <body className="h-full">{children}</body>
    </html>
  )
}
