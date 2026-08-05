import { Rail } from "@/components/shell/Rail";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-[100dvh] overflow-hidden">
      <Rail />
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
    </div>
  );
}
