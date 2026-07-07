import { createFileRoute } from "@tanstack/react-router"
import { Skeleton } from "@/components/ui/skeleton"
import { AppShell } from "@/components/AppShell"
import { JiraDispatchForm } from "@/components/JiraDispatchForm"
import { RequireLogin } from "@/lib/auth-redirect"
import { useSession } from "@/lib/session"

export const Route = createFileRoute("/jira")({
  component: JiraPage,
})

function JiraPage() {
  const session = useSession()

  if (session.isLoading) {
    return (
      <main className="p-6">
        <Skeleton className="h-64 w-full" />
      </main>
    )
  }
  if (!session.data) return <RequireLogin />

  return (
    <AppShell
      user={session.data}
      title="Jira Issues"
      description="Dispatch the agent to work on a Jira issue."
    >
      <JiraDispatchForm />
    </AppShell>
  )
}
