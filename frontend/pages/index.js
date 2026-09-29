import Head from 'next/head';
import Layout from '../components/Layout';
import EmptyState from '../components/EmptyState';

// Taak 3.4: landing page met lege staat voor nieuwsartikelen.
// De layout blijft bruikbaar bij 360px mobiele breedte (taak 3.3: mobile-first).
export default function Home() {
  return (
    <>
      <Head>
        <title>Nieuws Piet</title>
        <meta
          name="description"
          content="Lokale persoonlijke nieuwsdashboard voor één gebruiker."
        />
      </Head>
      <Layout>
        <EmptyState />
      </Layout>
    </>
  );
}
