export const SORTS = [
  ["-average_rating", "Highest rated"], ["average_rating", "Lowest rated"],
  ["-review_count", "Most reviewed"], ["review_count", "Fewest reviewed"],
] as const;
export type Sort = typeof SORTS[number][0];
export type ListingQuery = { industries: string[]; sort: Sort; page: number; pageSize: number };

function positiveInteger(params: URLSearchParams, key: string, fallback: number): number {
  const values = params.getAll(key);
  if (!values.length) return fallback;
  const value = values[0];
  if (values.length !== 1 || !/^[0-9]+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 1) {
    throw new Error(`${key} must be a positive integer.`);
  }
  return Number(value);
}

export function readQuery(search: string): ListingQuery {
  const params = new URLSearchParams(search);
  const sortValues = params.getAll("sort");
  const sort = sortValues[0] ?? "-average_rating";
  if (sortValues.length > 1 || !SORTS.some(([value]) => value === sort)) throw new Error("Choose a supported sorting option.");
  const pageSize = positiveInteger(params, "page_size", 20);
  if (pageSize > 100) throw new Error("Page size must be between 1 and 100.");
  const industries = [...new Set(params.getAll("industry"))];
  if (industries.some((value) => !value)) throw new Error("Industry selections cannot be empty.");
  return { industries, sort: sort as Sort, page: positiveInteger(params, "page", 1), pageSize };
}

export function queryString(query: ListingQuery): string {
  const params = new URLSearchParams();
  query.industries.forEach((value) => params.append("industry", value));
  if (query.sort !== "-average_rating") params.set("sort", query.sort);
  if (query.page !== 1) params.set("page", String(query.page));
  if (query.pageSize !== 20) params.set("page_size", String(query.pageSize));
  const search = params.toString();
  return search ? `?${search}` : "";
}

export function listingHref(query: ListingQuery): string { return `/brand/${queryString(query)}`; }
