// The project's two videos, in the family's film-slot markup (styles in family.css).
// Adapted from quartic-query-lean site/src/family/FilmSlot.tsx, itself adapted from
// lean-exposition site/src/app/FilmSlot.tsx (Apache-2.0). The picture and the title open
// the same video, so the title is the one link in the Tab order and the picture is hidden
// from assistive technology. Stills are local files; the page requests nothing from YouTube.

interface Film {
  id: string;
  title: string;
  youtube: string;
  seconds: number;
  still: string;
}

export const SHORT_FILM: Film = {
  id: "short",
  title: "Short video",
  youtube: "https://www.youtube.com/watch?v=9-5YJ6SoT4Y",
  seconds: 95,
  still: "films/short-code-ontology-640.webp",
};

export const LONG_FILM: Film = {
  id: "long",
  title: "Full video",
  youtube: "https://www.youtube.com/watch?v=zrVv-a8rT_s",
  seconds: 278,
  still: "films/long-code-ontology-640.webp",
};

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function spoken(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m} minute${m === 1 ? "" : "s"}${s ? ` ${s} seconds` : ""}`;
}

export function FilmThumb({ film, size }: { film: Film; size: "small" | "large" }) {
  return (
    <figure className={`film-slot film-slot--${size} film-thumb film-thumb--${film.id}`}>
      <a className="film-slot__frame" href={film.youtube} target="_blank" rel="noopener noreferrer" aria-hidden="true" tabIndex={-1}>
        <img src={`${import.meta.env.BASE_URL}${film.still}`} alt="" width={640} height={360} decoding="async" />
        <span className="film-slot__play" />
        <span className="film-slot__time">{clock(film.seconds)}</span>
      </a>
      <figcaption className="film-slot__caption">
        <p className="film-slot__title">
          <a href={film.youtube} target="_blank" rel="noopener noreferrer">
            {film.title}
            <span className="visually-hidden">, on YouTube, {spoken(film.seconds)}</span>
          </a>
        </p>
      </figcaption>
    </figure>
  );
}

/** The short video large and the full video smaller, their pictures sharing a lower edge. */
export function FilmPair({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`film-pair ${compact ? "film-pair--compact" : ""}`} role="group" aria-label="Videos about this project">
      <FilmThumb film={SHORT_FILM} size={compact ? "small" : "large"} />
      <FilmThumb film={LONG_FILM} size="small" />
    </div>
  );
}
