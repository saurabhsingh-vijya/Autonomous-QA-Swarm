import { Construction } from "lucide-react";
import { EmptyState, PageHeader } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import type { ScreenDef } from "./registry";

export function PlaceholderScreen({ screen }: { screen: ScreenDef }) {
  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Home", to: "/" }, { label: screen.navLabel }]}
        title={screen.name}
        subtitle={screen.purpose}
      />
      <EmptyState
        icon={Construction}
        title={`Planned in slice ${screen.plannedSlice}`}
        description="Not implemented in this phase. Nothing shown here is fabricated: this screen will read real data once its slice lands."
      />
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
