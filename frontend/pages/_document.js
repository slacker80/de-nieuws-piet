import { Html, Head, Main, NextScript } from 'next/document';

// Taak 3.5: PWA manifest met valid linked manifest.
// Het manifest ligt in public/manifest.json en wordt hier gekoppeld via
// <link rel="manifest">; viewport en theme-color horen bij dezelfde PWA-setup.
export default function Document() {
  return (
    <Html lang="nl">
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#0f172a" />
        <link rel="manifest" href="/manifest.json" />
        <link rel="icon" href="/icons/icon-192.png" />
        <link rel="apple-touch-icon" href="/icons/icon-192.png" />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
