import { Skeleton } from "@/components/ui/skeleton"
import { RequireLogin } from "@/lib/auth-redirect"
import { AppShell } from "@/components/AppShell"
import { JiraDispatchForm } from "@/components/JiraDispatchForm"
import { useSession } from "@/lib/session"
import { createFileRoute } from "@tanstack/react-router"

export const Route = createFileRoute("/")({ component: Index })

function Index() {
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
