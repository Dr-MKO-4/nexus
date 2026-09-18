import { useQuery } from "@tanstack/react-query";

import { getPendingValidations } from "@/services/api";
import type { HITLRequest } from "@/types";

export function useHITLPending() {
  return useQuery<HITLRequest[]>({
    queryKey: ["hitl-pending"],
    queryFn: getPendingValidations,
    refetchInterval: 10_000, // spec : "polling 10s"
  });
}
