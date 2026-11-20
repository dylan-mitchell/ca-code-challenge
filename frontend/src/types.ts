export type Industry = { slug: string; name: string };
export type SelectedReview = {
  id: string; slug: string; title: string; rating: number;
  reviewer_name: string; published_at: string; snippet: string;
};
export type Brand = {
  id: string; slug: string; name: string; industries: Industry[];
  average_rating: number | null; review_count: number;
  short_description: string; top_review: SelectedReview | null;
};
export type BrandPage = {
  count: number; next: string | null; previous: string | null;
  results: Brand[]; available_industries: Industry[];
};

const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const text = (value: unknown): value is string => typeof value === "string";
const integer = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const rating = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 1 && value <= 5;
const industry = (value: unknown): value is Industry => record(value) && text(value.slug) && text(value.name);
const selectedReview = (value: unknown): value is SelectedReview => record(value)
  && [value.id, value.slug, value.title, value.reviewer_name, value.snippet].every(text)
  && rating(value.rating) && Number.isInteger(value.rating)
  && text(value.published_at) && Number.isFinite(Date.parse(value.published_at));
const brand = (value: unknown): value is Brand => record(value)
  && [value.id, value.slug, value.name, value.short_description].every(text)
  && Array.isArray(value.industries) && value.industries.every(industry)
  && (value.average_rating === null || rating(value.average_rating))
  && integer(value.review_count) && (value.top_review === null || selectedReview(value.top_review));

export function parseBrandPage(value: unknown): BrandPage {
  if (!record(value) || !integer(value.count)
    || !(value.next === null || text(value.next)) || !(value.previous === null || text(value.previous))
    || !Array.isArray(value.results) || !value.results.every(brand)
    || !Array.isArray(value.available_industries) || !value.available_industries.every(industry)) {
    throw new Error("The brand service returned an unexpected response.");
  }
  return value as BrandPage;
}
