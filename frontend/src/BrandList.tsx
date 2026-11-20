import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { BrandCard } from "./BrandCard";
import { listingHref, readQuery, SORTS } from "./query";
import type { ListingQuery, Sort } from "./query";
import { parseBrandPage } from "./types";
import type { BrandPage, Industry } from "./types";

type Failure = { kind: "invalid" | "missing" | "temporary"; message: string };
type Outcome = { search: string; attempt: number } & (
  { status: "loading" } | { status: "success"; data: BrandPage } | { status: "error"; failure: Failure }
);

class RequestFailure extends Error {
  constructor(public failure: Failure) { super(failure.message); }
}

async function getPage(search: string, signal: AbortSignal): Promise<BrandPage> {
  const response = await fetch(`/api/brands/${search}`, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) {
    if (response.status === 400) throw new RequestFailure({ kind: "invalid", message: "This listing selection isn't valid. Reset the listing and choose your filters again." });
    if (response.status === 404) {
      const body: unknown = await response.json().catch(() => null);
      if (body && typeof body === "object" && "error" in body && body.error && typeof body.error === "object" && "code" in body.error && body.error.code === "page_not_found") {
        throw new RequestFailure({ kind: "missing", message: "This page of results is no longer available." });
      }
    }
    throw new Error("Brands could not be loaded.");
  }
  return parseBrandPage(await response.json());
}

export function BrandList() {
  const [search, setSearch] = useState(window.location.search);
  const [attempt, setAttempt] = useState(0);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [outcome, setOutcome] = useState<Outcome>({ search, attempt, status: "loading" });
  const resultsHeading = useRef<HTMLHeadingElement>(null);
  const industryFieldset = useRef<HTMLFieldSetElement>(null);
  const focusAfterPageChange = useRef(false);
  let query: ListingQuery | null = null;
  let invalidMessage = "";
  try { query = readQuery(search); } catch (error) { invalidMessage = error instanceof Error ? error.message : "Invalid listing selection."; }

  useEffect(() => {
    const restore = () => { focusAfterPageChange.current = false; setSearch(window.location.search); };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    if (invalidMessage) return;
    const controller = new AbortController();
    let current = true;
    let timedOut = false;
    setOutcome({ search, attempt, status: "loading" });
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 10000);
    getPage(search, controller.signal).then((data) => {
      if (!current) return;
      setIndustries(data.available_industries);
      setOutcome({ search, attempt, status: "success", data });
    }).catch((error: unknown) => {
      if (!current) return;
      setOutcome({ search, attempt, status: "error", failure: error instanceof RequestFailure ? error.failure : {
        kind: "temporary", message: timedOut ? "The request took too long. Please try again." : "We couldn't load brands right now. Please try again.",
      } });
    }).finally(() => window.clearTimeout(timeout));
    return () => { current = false; window.clearTimeout(timeout); controller.abort(); };
  }, [search, attempt, invalidMessage]);

  const isCurrent = outcome.search === search && outcome.attempt === attempt;
  const data = !invalidMessage && isCurrent && outcome.status === "success" ? outcome.data : null;
  const failure: Failure | null = invalidMessage ? { kind: "invalid", message: invalidMessage }
    : isCurrent && outcome.status === "error" ? outcome.failure : null;
  const loading = !data && !failure;

  useEffect(() => {
    if (data && focusAfterPageChange.current) {
      focusAfterPageChange.current = false;
      resultsHeading.current?.focus();
    }
  }, [data]);

  function navigate(href: string, focusResults = false) {
    if (`${window.location.pathname}${window.location.search}` === href) return;
    focusAfterPageChange.current = focusResults;
    window.history.pushState(null, "", href);
    setSearch(window.location.search);
  }
  function change(next: ListingQuery, paging = false) { navigate(listingHref(next), paging); }
  function followPage(event: MouseEvent<HTMLAnchorElement>, next: ListingQuery) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); change(next, true);
  }
  function clearIndustries() {
    if (query) {
      change({ ...query, industries: [], page: 1 });
      // The clear button disappears; keep keyboard focus in the filter controls.
      (industryFieldset.current?.querySelector("input") ?? industryFieldset.current)?.focus();
    }
  }

  const pageCount = query && data ? Math.ceil(data.count / query.pageSize) : 0;
  const countMessage = data ? `${data.count} ${data.count === 1 ? "brand" : "brands"} found.` : "";
  return <>
    <div className="directory-toolbar">
      <fieldset className="industry-filter" ref={industryFieldset} tabIndex={-1}>
        <legend>Filter by industry</legend>
        <div className="industry-filter__options">{industries.map((industry) => <label key={industry.slug} className="industry-filter__option">
          <input type="checkbox" checked={query?.industries.includes(industry.slug) ?? false} disabled={!query} onChange={(event) => {
            if (query) change({ ...query, page: 1, industries: event.target.checked ? [...query.industries, industry.slug] : query.industries.filter((slug) => slug !== industry.slug) });
          }} />{industry.name}
        </label>)}</div>
        <p className="industry-filter__hint">Choose any industries. No selection shows all brands.</p>
        {!!query?.industries.length && <button className="text-button" onClick={clearIndustries}>Clear industries</button>}
      </fieldset>
      <div className="sort-control"><label htmlFor="brand-sort">Sort brands</label><select id="brand-sort" value={query?.sort ?? ""} disabled={!query} onChange={(event) => {
        if (query) change({ ...query, sort: event.target.value as Sort, page: 1 });
      }}>{!query && <option value="">Invalid selection</option>}{SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    </div>
    <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{loading ? "Loading brands…" : failure ? failure.message : countMessage}</p>
    <section aria-labelledby="brand-results-heading" aria-busy={loading}>
      <h2 className={`results-heading${data?.count ? " results-summary" : " sr-only"}`} id="brand-results-heading" ref={resultsHeading} tabIndex={-1}>{data?.count && query
        ? `Showing ${(query.page - 1) * query.pageSize + 1}–${Math.min(query.page * query.pageSize, data.count)} of ${data.count} brands`
        : "Brand results"}</h2>
      {loading && <div className="loading-state"><span className="loading-state__bar" aria-hidden="true" /><p>Loading brands…</p></div>}
      {failure && <div className="error-state"><h3>{failure.kind === "invalid" ? "Check your listing selection" : failure.kind === "missing" ? "Page not found" : "Unable to load brands"}</h3><p>{failure.message}</p>
        {failure.kind === "invalid" ? <a href="/brand/" className="button button--secondary" onClick={(event) => {
          if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate("/brand/"); }
        }}>Reset listing</a> : failure.kind === "missing" && query ? <a className="button button--secondary" href={listingHref({ ...query, page: 1 })} onClick={(event) => followPage(event, { ...query, page: 1 })}>Go to first page</a>
          : <button className="button button--secondary" onClick={() => setAttempt((value) => value + 1)}>Try again</button>}
      </div>}
      {data && query && (data.count > 0 ? <>
        <div className="card-grid">{data.results.map((brand) => <BrandCard brand={brand} key={brand.id} />)}</div>
        {pageCount > 1 && <nav className="pagination" aria-label="Brand pagination">
          {data.previous ? <a className="button button--secondary" href={listingHref({ ...query, page: query.page - 1 })} onClick={(event) => followPage(event, { ...query, page: query.page - 1 })}>Previous</a> : <span className="pagination__disabled" aria-disabled="true">Previous</span>}
          <span className="pagination__position">Page {query.page} of {pageCount}</span>
          {data.next ? <a className="button button--secondary" href={listingHref({ ...query, page: query.page + 1 })} onClick={(event) => followPage(event, { ...query, page: query.page + 1 })}>Next</a> : <span className="pagination__disabled" aria-disabled="true">Next</span>}
        </nav>}
      </> : <div className="empty-state"><h3>{query.industries.length ? "No brands match these industries" : "No brands are available yet"}</h3><p>{query.industries.length ? "Try removing your industry filters to see more brands." : "Check back soon for customer experiences and brand reviews."}</p>{query.industries.length > 0 && <button className="button button--secondary" onClick={clearIndustries}>Clear industries</button>}</div>)}
    </section>
  </>;
}
