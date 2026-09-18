import { useQuery } from "@tanstack/react-query";

import { getAgents } from "@/services/api";
import type { Agent } from "@/types";

export function useAgents() {
  return useQuery<Agent[]>({
    queryKey: ["agents"],
    queryFn: getAgents,
    refetchInterval: 5_000, // spec : "polling 5s"
  });
}
