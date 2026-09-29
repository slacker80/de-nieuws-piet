// Gedeelde pagina-layout (taken 3.2/3.3): semantische landmarks `nav` en
// `main`, mobile-first en vloeiend bij 360px breedte.
export default function Layout({ children }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <nav className="app-nav" aria-label="Hoofdnavigatie">
          <a className="app-nav__brand" href="/">
            Nieuws Piet
          </a>
          <ul className="app-nav__list">
            <li>
              <a href="/">Vandaag</a>
            </li>
            <li>
              <a href="/#rubrieken">Rubrieken</a>
            </li>
            <li>
              <a href="/#instellingen">Instellingen</a>
            </li>
          </ul>
        </nav>
      </header>

      <main className="app-main" id="hoofdinhoud">
        {children}
      </main>

      <footer className="app-footer">
        <p>Lokale, niet-publieke nieuwsdashboard. Alleen bereikbaar op je eigen netwerk.</p>
      </footer>
    </div>
  );
}
