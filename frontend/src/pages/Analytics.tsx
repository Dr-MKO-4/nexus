/**
 * Page Analytics  ajoutée pour Prompt 8.3 : le spec de ce prompt (routing/
 * navigation) liste explicitement "/analytics" comme route et "Analytics"
 * comme item de navigation (icône BarChart2), mais aucun prompt (8.2 inclus)
 * n'a jamais demandé la construction du fichier de page correspondant  sans
 * lui, cette route mènerait nulle part. Construite ici avec les données déjà
 * réelles (KPIs, performance par canal, rapports) déjà utilisées ailleurs.
 */
import { useState } from "react";

import { Dialog, DialogContent, DialogTitle, EmptyState, LoadingState } from "@/components/ui";
import { useActiveClientId, useAnomalies, useChannelPerformanceQuery, useKPIs, useReportDetail, useReports } from "@/hooks";

export default function Analytics() {
  const clientId = useActiveClientId();
  const kpis = useKPIs(clientId ?? undefined);
  const channels = useChannelPerformanceQuery(clientId ?? undefined);
  const reports = useReports(clientId ?? undefined);
  const anomalies = useAnomalies(clientId ?? undefined);
  const [openReportId, setOpenReportId] = useState<string | null>(null);

  if (!clientId) {
    return <EmptyState message="Aucun client actif  aucun endpoint de liste des clients n'existe pour les comptes admin." />;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-50">Analyses</h1>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-50">KPIs (7 derniers jours)</h2>
        {kpis.isLoading ? (
          <LoadingState />
        ) : !kpis.data?.length ? (
          <EmptyState message="Aucun KPI disponible." />
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {kpis.data.map((kpi) => (
                <tr key={kpi.metric_name} className="border-b border-neutral-100 dark:border-neutral-900">
                  <td className="py-1 text-neutral-500">{kpi.metric_name}</td>
                  <td className="text-right font-medium">{kpi.metric_value.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Performance par canal</h2>
        {channels.isLoading ? (
          <LoadingState />
        ) : !channels.data?.length ? (
          <EmptyState message="Aucune donnée de canal disponible." />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {channels.data.map((channel) => (
              <div key={channel.channel} className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
                <p className="mb-1 text-sm font-medium capitalize">{channel.channel}</p>
                {Object.entries(channel.metrics).map(([name, value]) => (
                  <p key={name} className="flex justify-between text-xs text-neutral-500">
                    <span>{name}</span>
                    <span>{value}</span>
                  </p>
                ))}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Anomalies détectées</h2>
        {anomalies.isLoading ? (
          <LoadingState />
        ) : !anomalies.data?.length ? (
          <EmptyState message="Aucune anomalie détectée." />
        ) : (
          <ul className="space-y-1 text-sm">
            {anomalies.data.map((anomaly) => (
              <li key={anomaly.id} className="rounded-md border border-amber-200 bg-amber-50 p-2 dark:border-amber-900 dark:bg-amber-950">
                <p className="text-xs text-amber-500">{new Date(anomaly.created_at).toLocaleString()}</p>
                <pre className="mt-1 overflow-auto text-xs text-amber-800 dark:text-amber-200">
                  {JSON.stringify(anomaly.decision_data, null, 2)}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-50">Rapports générés</h2>
        {reports.isLoading ? (
          <LoadingState />
        ) : !reports.data?.length ? (
          <EmptyState message="Aucun rapport généré." />
        ) : (
          <ul className="space-y-1 text-sm">
            {reports.data.map((report) => (
              <li key={report.id} className="flex justify-between border-b border-neutral-100 py-1 dark:border-neutral-900">
                <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => setOpenReportId(report.id)}>
                  {report.report_type} — {report.period ?? ""}
                </button>
                <span className="text-neutral-400">{report.delivered_at ? new Date(report.delivered_at).toLocaleString() : "Non livré"}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {openReportId && <ReportDetailDialog reportId={openReportId} onClose={() => setOpenReportId(null)} />}
    </div>
  );
}

function ReportDetailDialog({ reportId, onClose }: { reportId: string; onClose: () => void }) {
  const { data, isLoading } = useReportDetail(reportId);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogTitle>Détail du rapport</DialogTitle>
        {isLoading ? (
          <LoadingState />
        ) : !data ? (
          <EmptyState message="Rapport introuvable." />
        ) : (
          <pre className="mt-4 max-h-[60vh] overflow-auto text-xs text-neutral-600 dark:text-neutral-400">
            {JSON.stringify(data.content, null, 2)}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}
