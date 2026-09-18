import { useQuery } from "@tanstack/react-query";

import { getProviderStatus, type ProviderStatus } from "@/services/api";

export function useProviderStatus() {
  return useQuery<ProviderStatus[]>({
    queryKey: ["provider-status"],
    queryFn: getProviderStatus,
  });
}
