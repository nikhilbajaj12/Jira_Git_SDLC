import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useState } from "react"

import type { JiraDispatchBody, JiraDispatchResponse, ApiError } from "@/lib/api"
import { SettingsRow, SettingsSection } from "@/components/AppShell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { AlertCircle } from "lucide-react"
import { api } from "@/lib/api"
import { useRepos } from "@/lib/profile"
import { RepoSelector } from "@/components/agents/RepoSelector"

export function JiraDispatchForm() {
  const repos = useRepos()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [issueKey, setIssueKey] = useState("")
  const [summary, setSummary] = useState("")
  const [description, setDescription] = useState("")
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const dispatchMutation = useMutation({
    mutationFn: (body: JiraDispatchBody) => api.jiraDispatch(body),
    onSuccess: (data: JiraDispatchResponse) => {
      qc.invalidateQueries({ queryKey: ["agent-threads"] })
      setError(null)
      if (!data.thread_id) {
        setError("Agent was dispatched but no thread was created. Check server logs.")
        return
      }
      if (data.status === "error") {
        setError(data.error || "Agent dispatch failed on the server")
        return
      }
      navigate({ to: `/agents/${data.thread_id}` })
    },
    onError: (err: Error) => {
      const apiErr = err as ApiError
      if (apiErr.status === 401) {
        setError("You need to log in again. Please refresh the page.")
      } else if (apiErr.status === 403) {
        setError("Access denied. Check your permissions.")
      } else {
        setError(err.message || "An unexpected error occurred. Check that the backend server is running.")
      }
    },
  })

  const handleSubmit = () => {
    if (!selectedRepo) {
      setError("Please select a repository")
      return
    }
    const parts = selectedRepo.split("/")
    const repo_owner = parts[0] ?? ""
    const repo_name = parts.slice(1).join("/") || ""

    dispatchMutation.mutate({
      issue_key: issueKey || undefined,
      summary,
      description: description || undefined,
      repo_owner,
      repo_name,
    })
  }

  const canSubmit =
    (issueKey.trim() || summary.trim()) &&
    selectedRepo &&
    !dispatchMutation.isPending

  return (
    <>
      <SettingsSection title="Issue Details">
        <div className="divide-y divide-border">
          <SettingsRow
            label="Jira Issue Key"
            description="Optional. E.g. PROJ-123. If provided, the agent fetches full details from Jira."
            htmlFor="issue-key"
            control={
              <Input
                id="issue-key"
                className="w-56"
                placeholder="PROJ-123"
                value={issueKey}
                onChange={(e) => setIssueKey(e.target.value)}
              />
            }
          />
          <SettingsRow
            label="Summary"
            description="Required if no issue key. Brief title of the task."
            htmlFor="summary"
            control={
              <Input
                id="summary"
                className="w-80"
                placeholder="Fix login validation"
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
              />
            }
          />
          <div className="px-4 py-3">
            <Label htmlFor="description" className="mb-1.5 block text-xs font-medium text-foreground">
              Description
            </Label>
            <p className="mb-2 text-xs text-muted-foreground">
              Optional. Detailed description of the issue.
            </p>
            <Textarea
              id="description"
              placeholder="Describe the issue in detail..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
            />
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Repository">
        <div className="px-4 py-3">
          <p className="mb-2 text-xs text-muted-foreground">
            Select the repository where the agent will implement changes.
          </p>
          {repos.data?.repositories.length ? (
            <RepoSelector
              repos={repos.data.repositories}
              selectedRepo={selectedRepo}
              onRepoChange={setSelectedRepo}
              placeholder="Pick a repository\u2026"
              emptySelectionLabel="No repository selected"
              triggerClassName="h-8 w-full max-w-xs rounded-md border border-input bg-input/20 px-2 py-1.5 text-xs/relaxed text-foreground transition-colors hover:opacity-100 dark:bg-input/30"
              dropdownClassName="w-80"
            />
          ) : (
            <Input
              className="w-80"
              placeholder="owner/repo"
              value={selectedRepo ?? ""}
              onChange={(e) => setSelectedRepo(e.target.value)}
            />
          )}
        </div>
      </SettingsSection>

      {error && (
        <div className="rounded border border-red-500/50 bg-red-50 px-4 py-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-400">
          <span className="flex items-center gap-1.5">
            <AlertCircle className="h-3.5 w-3.5" />
            <span className="font-medium">Error</span>
          </span>
          <p className="mt-1">{error}</p>
        </div>
      )}

      <div className="flex justify-end">
        <Button
          size="sm"
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          {dispatchMutation.isPending ? "Dispatching\u2026" : "Dispatch Agent"}
        </Button>
      </div>
    </>
  )
}
