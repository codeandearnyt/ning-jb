import { AppShell } from "@/components/app/AppShell";
import { providerStatuses } from "@/lib/providers";

export const dynamic = "force-dynamic";

export default function Page() {
  // Rendered on the server so the provider registry is usable on first paint —
  // no client fetch, no disabled control while a cold function wakes up.
  const providers = providerStatuses();

  return <AppShell providers={providers} />;
}
