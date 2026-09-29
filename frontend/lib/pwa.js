// Taak 3.6 — service-worker/offline status, expliciet ingesteld.
//
// Keuze voor deze bootstrap: service worker UITGESLOTEN. Er wordt geen
// service-worker bestand geschreven, geen registratie uitgevoerd en geen
// offline-cache aangelegd. De status is één centrale, uitleesbare vlag zodat
// het beleid expliciet is (in plaats van impliciet afwezig).
//
// Wanneer offline ondersteuning later gewenst is: enabled op true zetten en
// een service-worker bestand toevoegen; dit module regelt dan de registratie.
export const PWA_CONFIG = {
  name: 'Nieuws Piet',
  serviceWorker: {
    enabled: false,
    scope: '/',
    reason:
      'Bootstrap-fase: geen offline-cache nodig; de app draait lokaal op de LAN.',
  },
};

let applied = false;

// Registreert de service worker uitsluitend wanneer dat expliciet is aangezet.
// Idempotent: meerdere aanroepen registreren maximaal één keer.
export function applyServiceWorkerPolicy() {
  if (applied) return;
  applied = true;

  if (!PWA_CONFIG.serviceWorker.enabled) return;
  if (!('serviceWorker' in navigator)) return;

  navigator.serviceWorker
    .register(`${PWA_CONFIG.serviceWorker.scope}sw.js`)
    .catch(() => {
      // Registratie is optioneel; een falende registratie blokkeert de app niet.
    });
}
