import type { Metadata } from "next";

import { ReportView } from "@/components/ReportView";

export async function generateMetadata(props: PageProps<"/report/[ticker]">): Promise<Metadata> {
  const { ticker } = await props.params;
  return { title: `${ticker.toUpperCase()} · Equity Research Desk` };
}

export default async function ReportPage(props: PageProps<"/report/[ticker]">) {
  const ticker = (await props.params).ticker.toUpperCase();
  // Keyed by ticker, so moving to another report starts from a fresh stream and state.
  return <ReportView key={ticker} ticker={ticker} />;
}
