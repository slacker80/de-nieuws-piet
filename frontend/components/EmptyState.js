// Taak 3.4: lege staat voor nieuwsartikelen, ook bij 360px mobiele breedte.
// De marker-tekst `Nieuws Piet` en de lege-staat-tekst zijn exact wat de
// acceptatietests en de frontend smoke verificatie zoeken.
export default function EmptyState() {
  return (
    <section className="empty-state" aria-labelledby="lege-stand-titel">
      <h1 id="lege-stand-titel">Nieuws Piet</h1>
      <p className="empty-state__lead">
        Jouw persoonlijke overzicht van het lokale nieuws.
      </p>
      <p className="empty-state__message" id="lege-stand">
        Nog geen nieuws beschikbaar
      </p>
      <p className="empty-state__hint">
        Zodra de eerste bronnen zijn toegevoegd, verschijnen hier de artikelen.
      </p>
    </section>
  );
}
