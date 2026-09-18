import { getAgentDisplayStatus, type Agent } from "@/types";
import { cn } from "@/lib/utils";
import { Badge } from "./badge";
import { StatusIndicator } from "./status-indicator";

export interface AgentCardProps {
  agent: Agent;
  className?: string;
}

export function AgentCard({ agent, className }: AgentCardProps) {
  const status = getAgentDisplayStatus(agent);
  const isError = status === "error";

  return (
    <div className={cn(
      "border-2 border-border p-4",
      isError && "border-destructive/40 bg-destructive/5",
      className
    )}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-black capitalize text-foreground tracking-tight">
          {agent.name}
        </h3>
        <div className="flex items-center gap-2">
          <StatusIndicator status={status} />
          <Badge variant={status} className="rounded-none text-[10px] font-bold uppercase tracking-wide px-1.5">
            {status}
          </Badge>
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-1.5 text-xs text-muted-foreground">
        <div>
          <dt className="text-[10px] uppercase tracking-wider">Queue</dt>
          <dd className="font-semibold text-foreground mt-0.5">{agent.queue}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wider">Profondeur</dt>
          <dd className="font-semibold text-foreground mt-0.5">{agent.queue_depth}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-[10px] uppercase tracking-wider">Dernière action</dt>
          <dd className="font-semibold text-foreground mt-0.5">
            {agent.last_decision_at
              ? new Date(agent.last_decision_at).toLocaleString()
              : "Aucune"}
          </dd>
        </div>
      </dl>
    </div>
  );
}
