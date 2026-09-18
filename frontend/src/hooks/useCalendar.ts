import { useQuery } from "@tanstack/react-query";

import { getCalendar } from "@/services/api";
import type { Content } from "@/types";

/** `GET /contents/calendar` (backend) exige des bornes ISO 8601 explicites,
 * pas un "mois"  cette fonction traduit `month` (n'importe quel `Date` du
 * mois visé) en bornes premier/dernier jour, la seule pièce spécifique au
 * concept "calendrier éditorial par mois" du spec. */
function monthBounds(month: Date): { start: string; end: string } {
  const start = new Date(month.getFullYear(), month.getMonth(), 1);
  const end = new Date(month.getFullYear(), month.getMonth() + 1, 0, 23, 59, 59);
  return { start: start.toISOString(), end: end.toISOString() };
}

export function useCalendar(clientId: string | undefined, month: Date) {
  const { start, end } = monthBounds(month);
  return useQuery<Content[]>({
    queryKey: ["calendar", clientId, start, end],
    queryFn: () => getCalendar(clientId!, start, end),
    enabled: Boolean(clientId),
  });
}
