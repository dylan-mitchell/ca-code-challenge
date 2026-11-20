import type { Brand } from "./types";

export function BrandCard({ brand }: { brand: Brand }) {
  const href = `/brand/${encodeURIComponent(brand.slug)}/`;
  const review = brand.top_review;
  return <article className="brand-card">
    <div className="badge-list">{brand.industries.map((industry) => <span className="badge" key={industry.slug}>{industry.name}</span>)}</div>
    <h3 className="brand-card__title"><a href={href}>{brand.name}</a></h3>
    <p className="rating">{brand.average_rating === null
      ? <span className="muted">Not rated yet</span>
      : <><span className="stars" aria-hidden="true">★</span> <strong>{brand.average_rating.toFixed(2)}</strong><span className="muted"> / 5 · {brand.review_count} {brand.review_count === 1 ? "review" : "reviews"}</span></>}
    </p>
    {brand.short_description && <p className="brand-card__description">{brand.short_description}</p>}
    {review && <div className="editor-pick">
      <p className="editor-pick__label">Editor's pick</p>
      <p className="editor-pick__snippet"><a href={`/review/${encodeURIComponent(review.slug)}/`}>{review.title}</a></p>
      <p className="editor-pick__snippet">{review.snippet}</p>
      <p className="editor-pick__byline">{review.reviewer_name} · {review.rating} / 5 · <time dateTime={review.published_at}>{new Date(review.published_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}</time></p>
    </div>}
    <div className="brand-card__footer"><a className="text-link" href={href}>View reviews <span aria-hidden="true">→</span><span className="sr-only"> for {brand.name}</span></a></div>
  </article>;
}
