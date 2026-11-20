import { describe, expect, it } from "vitest";
import { listingHref, readQuery } from "./query";
import { parseBrandPage } from "./types";

describe("listing URLs", () => {
  it("round trips repeated industries and nondefault sorting/paging", () => {
    const query = readQuery("?industry=insurance&industry=finance&sort=review_count&page=3&page_size=2");
    expect(query.industries).toEqual(["insurance", "finance"]);
    expect(readQuery(listingHref(query).split("?")[1])).toEqual(query);
    expect(listingHref(readQuery(""))).toBe("/brand/");
    expect(readQuery("?page=01&page_size=02")).toMatchObject({ page: 1, pageSize: 2 });
  });
  it.each(["?sort=bad", "?sort=review_count&sort=average_rating", "?page=0", "?page=2.5", "?page=1&page=2", "?page_size=101", "?page_size=", "?industry="])("rejects invalid values without falling back: %s", (search) => {
    expect(() => readQuery(search)).toThrow();
  });
  it("rejects malformed API responses instead of rendering partial cards", () => {
    expect(() => parseBrandPage({ count: 1, next: null, previous: null, results: [{}], available_industries: [] })).toThrow();
  });
});
