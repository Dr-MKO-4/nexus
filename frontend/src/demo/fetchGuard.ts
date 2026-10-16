/**
 * Interception de `fetch` en démo : seul le flux SSE authentifié
 * (GET /sse/content-stream/{id}, onglet Visuels) passe par `fetch` dans ce
 * frontend. Il est servi localement sous forme de trames `data: {...}`
 * comme le ferait backend/api/sse/streams.py. Toute autre requête vers
 * l'API est refusée localement (aucun backend en démo).
 */
const TEXT =
  "Brief visuel : table de brunch vue du dessus, lumière du matin, tons chauds et naturels, logo discret en bas à droite, format carré 1080x1080 pour Meta.";

export function installFetchGuard(): void {
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.includes("/sse/content-stream/")) {
      const words = TEXT.split(/(?<= )/);
      const encoder = new TextEncoder();
      const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const word of words) {
            await new Promise((r) => setTimeout(r, 90));
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ token: word })}\n\n`));
          }
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ token: "", done: true })}\n\n`));
          controller.close();
        },
      });
      return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    }
    if (/^\/api\//.test(url) || /localhost:8000/.test(url)) {
      return new Response(JSON.stringify({ detail: "Démo : aucun backend." }), { status: 503, headers: { "Content-Type": "application/json" } });
    }
    return original(input, init);
  };
}
