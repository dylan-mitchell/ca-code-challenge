import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BrandList } from "./BrandList";
import type { Brand, BrandPage } from "./types";

const industries = [{ slug: "insurance", name: "Insurance" }, { slug: "finance", name: "Finance" }];
const acme: Brand = { id: "1", name: "Acme", slug: "acme", industries, average_rating: 4.5, review_count: 2, short_description: "A useful service.", top_review: null };
const page = (overrides: Partial<BrandPage> = {}): BrandPage => ({ count: 1, next: null, previous: null, results: [acme], available_industries: industries, ...overrides });
const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
beforeEach(() => {
  window.history.replaceState(null, "", "/brand/");
  fetchMock = vi.fn<typeof fetch>().mockImplementation(() => response(page()));
  vi.stubGlobal("fetch", fetchMock);
});

describe("BrandList", () => {
  it("loads the URL, renders plain text, and shows only a selected editor pick", async () => {
    window.history.replaceState(null, "", "/brand/?industry=insurance&page_size=2");
    fetchMock.mockImplementation(() => response(page({ results: [{ ...acme, top_review: { id: "4", slug: "helpful", title: "Helpful perspective", rating: 3, reviewer_name: "Sarah", published_at: "2025-01-01T12:00:00Z", snippet: "<strong>Plain text</strong>" } }] })));
    render(<BrandList />);
    expect(await screen.findByRole("link", { name: "Acme" })).toHaveAttribute("href", "/brand/acme/");
    expect(fetchMock).toHaveBeenCalledWith("/api/brands/?industry=insurance&page_size=2", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.getByRole("checkbox", { name: "Insurance" })).toBeChecked();
    expect(screen.getByText("<strong>Plain text</strong>")).toBeVisible();
    expect(screen.getByRole("link", { name: "Helpful perspective" })).toHaveAttribute("href", "/review/helpful/");
  });

  it("applies OR filters immediately, resets page once, and preserves page size and sorting", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/brand/?industry=insurance&sort=review_count&page=3&page_size=2");
    const push = vi.spyOn(window.history, "pushState");
    render(<BrandList />);
    await screen.findByRole("link", { name: "Acme" });
    const finance = screen.getByRole("checkbox", { name: "Finance" });
    await user.click(finance);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(window.location.search).toBe("?industry=insurance&industry=finance&sort=review_count&page_size=2");
    expect(push).toHaveBeenCalledTimes(1);
    expect(finance).toHaveFocus();
    await user.selectOptions(screen.getByRole("combobox", { name: "Sort brands" }), "average_rating");
    expect(window.location.search).toBe("?industry=insurance&industry=finance&sort=average_rating&page_size=2");
    await user.click(screen.getByRole("button", { name: "Clear industries" }));
    expect(window.location.search).toBe("?sort=average_rating&page_size=2");
    expect(screen.getByRole("checkbox", { name: "Insurance" })).toHaveFocus();
  });

  it("uses real pagination links and focuses results only after an explicit page change", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/brand/?page_size=2");
    fetchMock.mockResolvedValueOnce(await response(page({ count: 3, next: "http://localhost/api/brands/?page=2&page_size=2" })))
      .mockResolvedValueOnce(await response(page({ count: 3, previous: "http://localhost/api/brands/?page_size=2", results: [{ ...acme, id: "2", name: "Bravo" }] })));
    render(<BrandList />);
    const next = await screen.findByRole("link", { name: "Next" });
    expect(next).toHaveAttribute("href", "/brand/?page=2&page_size=2");
    await user.click(next);
    const heading = await screen.findByRole("heading", { name: "Showing 3–3 of 3 brands" });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/brand/?page_size=2");
    expect(screen.getByText("Next")).toHaveAttribute("aria-disabled", "true");
  });

  it("restores controls on popstate without adding history or stealing filter focus", async () => {
    const user = userEvent.setup();
    const push = vi.spyOn(window.history, "pushState");
    render(<BrandList />);
    await user.click(await screen.findByRole("checkbox", { name: "Insurance" }));
    expect(push).toHaveBeenCalledTimes(1);
    act(() => { window.history.replaceState(null, "", "/brand/?sort=-review_count"); window.dispatchEvent(new PopStateEvent("popstate")); });
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("-review_count"));
    expect(screen.getByRole("checkbox", { name: "Insurance" })).not.toBeChecked();
    expect(push).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("checkbox", { name: "Insurance" })).toHaveFocus();
  });

  it.each(["success", "error"])("hides stale cards and ignores a superseded request's late %s", async (late) => {
    const user = userEvent.setup();
    const old = deferred<Response>();
    const fresh = deferred<Response>();
    fetchMock.mockResolvedValueOnce(await response(page())).mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise);
    render(<BrandList />);
    await user.click(await screen.findByRole("checkbox", { name: "Insurance" }));
    expect(screen.queryByRole("link", { name: "Acme" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Brand pagination" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Finance" }));
    expect((fetchMock.mock.calls[1][1]?.signal as AbortSignal).aborted).toBe(true);
    await act(async () => { fresh.resolve(await response(page({ results: [{ ...acme, name: "Current brand" }] }))); });
    expect(await screen.findByRole("link", { name: "Current brand" })).toBeVisible();
    await act(async () => { if (late === "error") old.reject(new Error("late error")); else old.resolve(await response(page({ results: [{ ...acme, name: "Stale brand" }] }))); });
    expect(screen.getByRole("link", { name: "Current brand" })).toBeVisible();
    expect(screen.queryByText("Unable to load brands")).not.toBeInTheDocument();
    expect(screen.queryByText("Stale brand")).not.toBeInTheDocument();
  });

  it("retries a failure without changing query or history", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/brand/?industry=insurance");
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    const push = vi.spyOn(window.history, "pushState");
    render(<BrandList />);
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Acme" })).toBeVisible();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/brands/?industry=insurance", "/api/brands/?industry=insurance"]);
    expect(push).not.toHaveBeenCalled();
  });

  it("aborts a timed-out request and provides a retry", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation((_url, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    try {
      render(<BrandList />);
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(screen.getByText("The request took too long. Please try again.", { selector: ".error-state p" })).toBeVisible();
      expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
      expect((fetchMock.mock.calls[0][1]?.signal as AbortSignal).aborted).toBe(true);
    } finally { vi.useRealTimers(); }
  });

  it("offers a working reset for an invalid initial request with no industry choices", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/brand/?industry=unknown");
    fetchMock.mockResolvedValueOnce(await response({ error: { code: "invalid_industry" } }, 400));
    render(<BrandList />);
    await user.click(await screen.findByRole("link", { name: "Reset listing" }));
    expect(window.location.search).toBe("");
    expect(await screen.findByRole("link", { name: "Acme" })).toBeVisible();
  });

  it("rejects invalid local query values visibly without requesting defaults", async () => {
    window.history.replaceState(null, "", "/brand/?page_size=101");
    render(<BrandList />);
    expect(screen.getByRole("link", { name: "Reset listing" })).toHaveAttribute("href", "/brand/");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("recovers a missing page while keeping industries, sort, and page size", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/brand/?industry=insurance&sort=review_count&page=8&page_size=2");
    fetchMock.mockResolvedValueOnce(await response({ error: { code: "page_not_found" } }, 404));
    render(<BrandList />);
    await user.click(await screen.findByRole("link", { name: "Go to first page" }));
    expect(window.location.search).toBe("?industry=insurance&sort=review_count&page_size=2");
    expect(await screen.findByRole("link", { name: "Acme" })).toBeVisible();
  });

  it("distinguishes an empty filtered result from an empty directory", async () => {
    window.history.replaceState(null, "", "/brand/?industry=insurance");
    fetchMock.mockImplementation(() => response(page({ count: 0, results: [] })));
    render(<BrandList />);
    expect(await screen.findByRole("heading", { name: "No brands match these industries" })).toBeVisible();
    fireEvent.click(screen.getAllByRole("button", { name: "Clear industries" })[0]);
    expect(await screen.findByRole("heading", { name: "No brands are available yet" })).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Brand pagination" })).not.toBeInTheDocument();
  });

  it("shows unrated brands without inventing an editor pick", async () => {
    fetchMock.mockImplementation(() => response(page({ results: [{ ...acme, average_rating: null, review_count: 0, short_description: "" }] })));
    render(<BrandList />);
    expect(await screen.findByText("Not rated yet")).toBeVisible();
    expect(screen.queryByText("Editor's pick")).not.toBeInTheDocument();
  });
});
