/**
 * Construcción del cliente de Microsoft Graph.
 *
 * Se monta la cadena por defecto del SDK (auth → retry → redirect → telemetry →
 * http) **sustituyendo** el RetryHandler por uno que no reintenta `POST`:
 *
 *  - Graph devuelve `429`/`503`/`504` con normalidad y conviene reintentar las
 *    lecturas.
 *  - `POST /me/sendMail` o `POST /me/events` NO son idempotentes: si el `503`
 *    llega después de que Microsoft procese la petición, reintentar envía el
 *    correo o la invitación dos veces.
 *
 * `Client.init({authProvider})` monta el RetryHandler por defecto sin este
 * filtro; `Client.initWithMiddleware` con `authProvider` **y** `middleware` a la
 * vez lanza `AmbiguityInInitialization`, por eso aquí solo se pasa la cadena.
 */
import {
  Client,
  MiddlewareFactory,
  RetryHandler,
  RetryHandlerOptions,
} from "@microsoft/microsoft-graph-client";

/** ¿Se puede reintentar este método HTTP? Fail-safe: lo desconocido, no. */
export function shouldRetryMethod(method: string | undefined | null): boolean {
  const verb = String(method ?? "GET").toUpperCase();
  // POST crea o envía; un reintento puede duplicar. El resto del tráfico del
  // servidor (GET, PATCH de Excel, PUT de subida) sí es seguro de reintentar.
  return verb !== "POST";
}

export function buildGraphClient(token: string): Client {
  const authProvider = { getAccessToken: async () => token };
  const chain = MiddlewareFactory.getDefaultMiddlewareChain(authProvider).filter(
    (m) => !(m instanceof RetryHandler),
  );
  const retry = new RetryHandler(
    new RetryHandlerOptions(3, 3, (_delay, _attempt, request, options) => {
      const method =
        (options as { method?: string } | undefined)?.method ??
        (request as Request | undefined)?.method;
      return shouldRetryMethod(method);
    }),
  );
  // Posición 1 = justo después del AuthenticationHandler, como en el SDK.
  chain.splice(1, 0, retry);
  return Client.initWithMiddleware({ middleware: chain });
}
