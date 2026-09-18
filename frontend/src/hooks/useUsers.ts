import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createUser, getUsers, updateUser, type CreateUserPayload } from "@/services/api";
import type { User, UserRole } from "@/types";

/** GET/POST/PATCH /users — Settings.tsx (section "Utilisateurs") gérait une
 * liste en useState LOCAL uniquement avant ce correctif (audit). */
export function useUsers(clientId: string | undefined) {
  return useQuery<User[]>({
    queryKey: ["users", clientId],
    queryFn: () => getUsers(clientId),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateUserPayload) => createUser(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role, is_active }: { id: string; role?: UserRole; is_active?: boolean }) =>
      updateUser(id, { role, is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}
