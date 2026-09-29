import '../styles/globals.css';
import { PWA_CONFIG, applyServiceWorkerPolicy } from '../lib/pwa';

// Taak 3.6: service-worker/offline status is EXPLICIET ingesteld in lib/pwa.js.
// In deze bootstrap is de service worker uitgesloten (PWA_CONFIG.serviceWorker.enabled
// === false); de applicatie registreert daarom nooit een service worker en biedt
// geen offline-cache. Zodra offline ondersteuning gewenst is, wordt daar de
// expliciete vlag omgezet.
export default function App({ Component, pageProps }) {
  if (typeof window !== 'undefined') {
    applyServiceWorkerPolicy();
  }

  return <Component {...pageProps} />;
}
