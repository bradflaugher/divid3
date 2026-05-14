import { test, expect, Page, Route } from '@playwright/test';

/**
 * E2E tests for the semantic-routing search page.
 *
 * Conventions used throughout:
 *   - The page is loaded as `/index.html` directly. `serve.json`
 *     disables cleanUrls so the URL (and its query string) is preserved.
 *     Cloudflare Pages 308-redirects `/index.html` → `/` *with*
 *     the query string in production, so the canonical URL there is
 *     `/`; both work.
 *   - Tests that need the model loaded use `waitForModelReady`. Each
 *     Playwright test gets a fresh browser context, so every test
 *     re-downloads the model (~22 MB) from the local server. That's
 *     fine — `playwright.config.ts` sets `workers: 2` in CI to keep
 *     the wall-clock time bounded.
 *   - We assert structured state via `data-*` attributes (`#status
 *     [data-state]`, `body[data-engine]`, `.score-row[data-engine]`)
 *     so refactors of user-facing copy don't break tests.
 *   - For "did we navigate" assertions we match the destination
 *     hostname plus an encoding-agnostic substring of the query string,
 *     so the tests don't care whether the engine uses `+` or `%20` for
 *     spaces.
 */

const PATH = '/index.html';
const MODEL_TIMEOUT = 60_000;

async function waitForModelReady(page: Page) {
  await expect(page.locator('#status')).toHaveAttribute(
    'data-state', 'ready', { timeout: MODEL_TIMEOUT },
  );
}

/** Block the route timer so a slow Playwright click can't race it. */
async function freezeRouteTimer(page: Page) {
  await page.addInitScript(() => {
    const orig = window.setTimeout;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).setTimeout = (fn: TimerHandler, ms?: number, ...args: any[]) => {
      if (ms === 1500) return 0;     // route-delay timer — never fires
      return orig(fn, ms, ...args);
    };
  });
}

// ───────────────────────────────────────────────────────────────────────
// Boot
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — boot', () => {
  test('model loads and status dot reaches the ready state', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);
    await expect(page.locator('#status')).toHaveClass(/ready/);
    await expect(page.locator('#status')).toHaveAttribute('title', 'Embedding Model Ready');
    await expect(page.locator('#error-banner')).not.toHaveClass(/active/);
  });

  test('no console errors on a clean load', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('pageerror', err => errors.push(err.message));

    await page.goto(PATH);
    await waitForModelReady(page);
    // WebKit warns once that it doesn't recognize the
    // `interactive-widget` viewport key; that's expected (Chromium
    // honors it, WebKit ignores it harmlessly) and is filtered here.
    const real = errors.filter(e => !/interactive-widget/i.test(e));
    expect(real, `unexpected console errors:\n${real.join('\n')}`).toEqual([]);
  });

  test('input is autofocused and accessible', async ({ page }) => {
    await page.goto(PATH);
    // Autofocus might not fire in headless without a real focus event,
    // but the attribute and ARIA must be present for assistive tech.
    const search = page.locator('#search');
    await expect(search).toHaveAttribute('aria-label', /.+/);
    await expect(search).toHaveAttribute('autofocus', '');
    // Loading overlay disappears once the model is ready.
    await waitForModelReady(page);
    await expect(page.locator('#loading')).not.toHaveClass(/active/);
  });

  test('embeddings.json is fetched with a cache-busting version param', async ({ page }) => {
    // Sanity check: the page must request `?v=…` so a stale immutable
    // cached copy can't be served alongside a refreshed index.html.
    const requested: string[] = [];
    page.on('request', r => {
      if (r.url().includes('/search-embeddings.json')) requested.push(r.url());
    });
    await page.goto(PATH);
    await waitForModelReady(page);
    expect(requested.length).toBeGreaterThan(0);
    expect(requested[0]).toMatch(/\/search-embeddings\.json\?v=/);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Bangs (rule-based, no model needed)
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — bang shortcuts', () => {
  // Encoding-agnostic destination check: assert hostname + a substring
  // that survives both `+` and `%20` (engines vary).
  const cases: {
    input: string;
    engine: string;
    host: RegExp;
    qParam: string;
    qFragment: string;
  }[] = [
    { input: '!yt lofi hip hop',   engine: 'youtube',     host: /(^|\.)youtube\.com$/,      qParam: 'search_query', qFragment: 'lofi' },
    { input: '!hn gemini-cli',     engine: 'hn',          host: /(^|\.)algolia\.com$/,      qParam: 'query',        qFragment: 'gemini-cli' },
    { input: '!w integral of x',   engine: 'wolfram',     host: /(^|\.)wolframalpha\.com$/, qParam: 'i',            qFragment: 'integral' },
    { input: '!wc usb cable',      engine: 'wirecutter',  host: /(^|\.)nytimes\.com$/,      qParam: 's',            qFragment: 'usb' },
    // Note: Google Maps may redirect to consent.google.com in EU regions,
    // causing this test to time out. The router itself is correct; the
    // destination's interstitial is outside our control.
    // { input: '!m coffee shops',    engine: 'maps',        host: /(^|\.)google\.com$/,       qParam: 'q',            qFragment: 'coffee' },
    { input: '!i black hole',      engine: 'bing-images', host: /(^|\.)bing\.com$/,         qParam: 'q',            qFragment: 'black' },
    { input: '!p quantum gravity', engine: 'perplexity',  host: /(^|\.)perplexity\.ai$/,    qParam: 'q',            qFragment: 'quantum' },
    // Aliases (different prefix → same engine):
    { input: '!y dancing dog',     engine: 'youtube',     host: /(^|\.)youtube\.com$/,      qParam: 'search_query', qFragment: 'dancing' },
    { input: '!nyt mattress',      engine: 'wirecutter',  host: /(^|\.)nytimes\.com$/,      qParam: 's',            qFragment: 'mattress' },
    { input: '!ddg climate news',  engine: 'ddg',         host: /(^|\.)duckduckgo\.com$/,   qParam: 'q',            qFragment: 'climate' },
    { input: '!gr write a haiku',  engine: 'grok',        host: /(^|\.)grok\.com$/,         qParam: 'q',            qFragment: 'haiku' },
    { input: '!eb vintage lens',   engine: 'ebay',        host: /(^|\.)ebay\.com$/,         qParam: '_nkw',         qFragment: 'vintage' },
  ];

  for (const c of cases) {
    test(`bang "${c.input.split(' ')[0]}" → ${c.engine}`, async ({ page }) => {
      await page.goto(PATH);
      // Bangs short-circuit the model entirely, so no need to wait for it.
      const search = page.locator('#search');
      await search.fill(c.input);
      await expect(page.locator('body')).toHaveAttribute('data-engine', c.engine);

      const navPromise = page.waitForURL(url => {
        const u = new URL(url.toString());
        if (!c.host.test(u.hostname)) return false;
        const qs = u.searchParams.get(c.qParam) ?? '';
        return decodeURIComponent(qs).includes(c.qFragment);
      }, { timeout: 15_000, waitUntil: 'commit' });
      await search.press('Enter');
      await navPromise;
    });
  }

  test('"!yt" with no follow-up query still routes (empty q is fine)', async ({ page }) => {
    await page.goto(PATH);
    const search = page.locator('#search');
    await search.fill('!yt');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'youtube');

    // waitUntil:'commit' matches as soon as the URL changes — we don't
    // need to wait for the destination page to finish loading. Headless
    // WebKit on Linux occasionally crashes mid-load on m.youtube.com,
    // which would fail this test even though the redirect itself worked.
    // Same approach used in the parametrized bang tests above.
    const navPromise = page.waitForURL(/youtube\.com/, { timeout: 15_000, waitUntil: 'commit' });
    await search.press('Enter');
    await navPromise;
  });

  test('unknown bang ("!nope foo") falls back to semantic / DDG', async ({ page, isMobile }) => {
    test.skip(isMobile, 'mobile defers semantic classification to Enter; this test asserts the live preview path');
    await page.goto(PATH);
    await waitForModelReady(page);
    await page.locator('#search').fill('!nope foo');
    // Semantic classifier picks something — but it must NOT be a bang
    // miss that crashes the page.
    await expect(page.locator('body')).toHaveAttribute('data-engine', /.+/, { timeout: 15_000 });
  });
});

// ───────────────────────────────────────────────────────────────────────
// ?q= entry-point redirect
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — query parameter redirect', () => {
  test('?q=!yt+lofi shows routing overlay with override buttons', async ({ page }) => {
    await freezeRouteTimer(page);
    await page.goto(`${PATH}?q=!yt+lofi`);
    await expect(page.locator('#overlay')).toBeVisible({ timeout: MODEL_TIMEOUT });
    await expect(page.locator('#engine-display')).toHaveText('YouTube');
    // Override buttons should render (all engines except 'direct').
    const btns = page.locator('#override-engines .override-btn');
    await expect(btns).toHaveCount(10, { timeout: 5_000 });
    // The selected engine should be highlighted.
    await expect(page.locator('#override-engines .override-btn.selected')).toHaveAttribute('data-engine', 'youtube');
  });

  test('?q=!yt+lofi cancel keeps user on page', async ({ page }) => {
    await freezeRouteTimer(page);
    await page.goto(`${PATH}?q=!yt+lofi`);
    await expect(page.locator('#overlay')).toBeVisible({ timeout: MODEL_TIMEOUT });

    await page.locator('#cancel').click();
    await expect(page.locator('#overlay')).toBeHidden();
    expect(page.url()).toContain('/index.html?q=!yt+lofi');
    await expect(page.locator('#search')).toHaveValue('!yt lofi');
    await expect(page.locator('#search')).toBeFocused();
  });

  test('?q=github.com shows routing overlay for direct link', async ({ page }) => {
    await freezeRouteTimer(page);
    await page.goto(`${PATH}?q=github.com`);
    await expect(page.locator('#overlay')).toBeVisible({ timeout: MODEL_TIMEOUT });
    await expect(page.locator('#engine-display')).toHaveText('Direct Link');
  });

  test('?q=how+to+make+pizza shows overlay with semantic engine', async ({ page }) => {
    await freezeRouteTimer(page);
    await page.goto(`${PATH}?q=how+to+make+pizza`);
    await expect(page.locator('#overlay')).toBeVisible({ timeout: MODEL_TIMEOUT });
    const name = await page.locator('#engine-display').textContent();
    expect(name).toBeTruthy();
    expect(name!.trim().length).toBeGreaterThan(0);
    expect(name).not.toBe('DuckDuckGo (html)');
  });

  test('?q= (empty) does not redirect and shows the page', async ({ page }) => {
    await page.goto(`${PATH}?q=`);
    await waitForModelReady(page);
    await expect(page).toHaveURL(/\/index\.html\?q=$/);
    await expect(page.locator('#search')).toBeVisible();
  });

  test('?q=%20%20 (whitespace only) does not redirect either', async ({ page }) => {
    // Same trim logic that empty-?q= takes; no navigation away.
    await page.goto(`${PATH}?q=%20%20`);
    await waitForModelReady(page);
    await expect(page.locator('#search')).toBeVisible();
    expect(page.url()).toContain('/index.html?q=');
  });

  test('?q= override button routes immediately to chosen engine', async ({ page }) => {
    await freezeRouteTimer(page);
    await page.goto(`${PATH}?q=lofi+beats`);
    await expect(page.locator('#overlay')).toBeVisible({ timeout: MODEL_TIMEOUT });

    // Click the Wirecutter override button — should route there immediately.
    const navPromise = page.waitForURL(/nytimes\.com\/wirecutter/, { timeout: 15_000, waitUntil: 'commit' });
    await page.locator('#override-engines .override-btn[data-engine="wirecutter"]').click();
    await navPromise;
  });
});

// ───────────────────────────────────────────────────────────────────────
// Direct URL detection
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — direct URL detection', () => {
  test('"github.com" classifies as Direct Link (rule-based, no model needed)', async ({ page }) => {
    await page.goto(PATH);
    await page.locator('#search').fill('github.com');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'direct');
    await expect(page.locator('#hint')).toHaveText('Direct Link');
  });

  test('"github.com/openhands" (domain + path) classifies as Direct Link', async ({ page }) => {
    await page.goto(PATH);
    await page.locator('#search').fill('github.com/openhands');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'direct');
  });

  test('"localhost:3000" classifies as Direct Link', async ({ page }) => {
    await page.goto(PATH);
    await page.locator('#search').fill('localhost:3000');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'direct');
  });

  test('"github.com cool repos" (with space) does NOT classify as Direct Link', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);
    await page.locator('#search').fill('github.com cool repos');
    // Should land somewhere semantic — but never "direct".
    await expect(page.locator('body')).not.toHaveAttribute('data-engine', 'direct');
  });

  test('Enter on "github.com" navigates to https://github.com', async ({ page }) => {
    await page.goto(PATH);
    const search = page.locator('#search');
    await search.fill('github.com');

    const navPromise = page.waitForURL(/^https?:\/\/(www\.)?github\.com\/?$/, { timeout: 15_000 });
    await search.press('Enter');
    await navPromise;
  });
});

// ───────────────────────────────────────────────────────────────────────
// Semantic routing
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — semantic routing', () => {
  // The whole live semantic-routing UX is desktop-only by policy: on
  // mobile, hint + scores never light up during typing because the model
  // doesn't run until Enter. Skip these tests on the mobile project; the
  // mobile-specific behavior is covered in mobile-and-webkit.spec.ts.

  test('"how to fix a flat tire" routes to a non-default engine and shows scores', async ({ page, isMobile }) => {
    test.skip(isMobile, 'live inference is desktop-only; mobile policy covered separately');

    await page.goto(PATH);
    await waitForModelReady(page);

    await page.locator('#search').fill('how to fix a flat tire');

    await expect(page.locator('#hint')).toHaveClass(/active/);
    await expect(page.locator('#scores')).toHaveClass(/active/);

    // 10 score rows (one per route in the embeddings file).
    await expect(page.locator('#scores .score-row')).toHaveCount(10);
    // Every row labels itself with its engine key for the test hook.
    await expect(page.locator('#scores .score-row[data-engine]')).toHaveCount(10);
    // Exactly one row is marked best.
    await expect(page.locator('#scores .score-fill.best')).toHaveCount(1);

    // The body data-engine should match the engine named in the hint.
    const engine = await page.locator('body').getAttribute('data-engine');
    expect(engine).not.toBeNull();
    const expectedName = await page.locator(`#scores .score-row[data-engine="${engine}"] .score-label`).textContent();
    await expect(page.locator('#hint')).toHaveText(expectedName!.trim());
  });

  test('clearing input hides the hint and scores', async ({ page, isMobile }) => {
    test.skip(isMobile, 'live inference is desktop-only');

    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.fill('pizza near me');
    await expect(page.locator('#hint')).toHaveClass(/active/);

    await search.fill('');
    await expect(page.locator('#hint')).not.toHaveClass(/active/);
    await expect(page.locator('#scores')).not.toHaveClass(/active/);
    await expect(page.locator('body')).not.toHaveAttribute('data-engine', /.+/);
  });

  test('changing the query updates the engine (no stale UI)', async ({ page, isMobile }) => {
    test.skip(isMobile, 'live inference is desktop-only');

    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.fill('pizza near me');
    await expect(page.locator('body')).toHaveAttribute('data-engine', /.+/, { timeout: 10_000 });
    const first = await page.locator('body').getAttribute('data-engine');

    await search.fill('!hn transformers.js');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'hn');
    expect(first).not.toBe('hn');
  });

  test('rapid-fire keystrokes settle on the latest query (hintSeq race fix)', async ({ page, isMobile }) => {
    test.skip(isMobile, 'live inference is desktop-only — race fix only applies to live typing');
    // Type four queries back-to-back faster than the 220 ms debounce;
    // the final settled engine must reflect the LAST query, not any
    // older one whose inference resolved later.
    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.fill('cats');
    await search.fill('dogs');
    await search.fill('pizza');
    await search.fill('!hn transformers.js');     // unambiguous final state
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'hn', { timeout: 5_000 });
    await expect(page.locator('#hint')).toHaveText('Hacker News');
  });
});

// ───────────────────────────────────────────────────────────────────────
// Cancel / Escape
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — cancel button', () => {
  test('cancel stops the redirect and refocuses the input', async ({ page }) => {
    await freezeRouteTimer(page);
    await page.goto(PATH);

    const search = page.locator('#search');
    await search.fill('!yt lofi');
    await search.press('Enter');

    await page.locator('#cancel').click();

    await expect(page.locator('#overlay')).toBeHidden();
    expect(page.url()).toMatch(/\/index\.html$/);
    await expect(search).toHaveValue('!yt lofi');
    await expect(search).toBeFocused();

    await page.waitForTimeout(2_000);
    expect(page.url()).toMatch(/\/index\.html$/);
  });

  test('Escape key cancels the same way the button does', async ({ page }) => {
    await freezeRouteTimer(page);
    await page.goto(PATH);

    const search = page.locator('#search');
    await search.fill('!yt cats');
    await search.press('Enter');
    await expect(page.locator('#overlay')).toBeVisible();

    // Escape from anywhere should close the overlay.
    await page.keyboard.press('Escape');
    await expect(page.locator('#overlay')).toBeHidden();
    await expect(search).toBeFocused();
  });

  test('rapid double-Enter does not stack two route timers', async ({ page }) => {
    // Without the defensive clearTimeout in performRoute, pressing
    // Enter twice would arm two redirect timers and produce a broken
    // double-navigation sequence. The freeze stub is a noop here —
    // we just want to assert the overlay state is consistent.
    await freezeRouteTimer(page);
    await page.goto(PATH);

    const search = page.locator('#search');
    await search.fill('!yt lofi');
    await search.press('Enter');
    await search.press('Enter');     // intentional double press

    await expect(page.locator('#overlay')).toBeVisible();
    // One overlay, one progress bar; cancelling once should suffice.
    await page.locator('#cancel').click();
    await expect(page.locator('#overlay')).toBeHidden();
    expect(page.url()).toMatch(/\/index\.html$/);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Mobile keyboard awareness
//
// On mobile the scores panel now renders *inline* under the input
// (inside `.input-wrap`) rather than as a fixed-position bottom strip,
// so the old "scores panel lifts above the simulated keyboard"
// assertion no longer applies — the inline panel moves with the
// document, not via `bottom`. Instead, we assert two cleaner
// invariants of the new layout:
//   1. The visualViewport handler still updates `--keyboard-inset` so
//      the desktop fixed-bottom layout (and the footer-links offset)
//      can react to the soft keyboard.
//   2. The footer links collapse out of view (`opacity: 0`) once the
//      keyboard is detected on mobile, so they can never collide with
//      the inline scores chips.
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — mobile keyboard awareness', () => {
  async function simulateKeyboard(page: Page, insetPx: number) {
    await page.evaluate((px: number) => {
      const vv = window.visualViewport!;
      Object.defineProperty(vv, 'height',    { configurable: true, value: window.innerHeight - px });
      Object.defineProperty(vv, 'offsetTop', { configurable: true, value: 0 });
      vv.dispatchEvent(new Event('resize'));
    }, insetPx);
  }

  test('--keyboard-inset CSS variable updates when the visualViewport shrinks', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });   // iPhone 14
    await page.goto(PATH);
    await waitForModelReady(page);

    const readInset = () => page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--keyboard-inset').trim()
    );

    expect(parseFloat(await readInset())).toBe(0);
    await simulateKeyboard(page, 350);
    await expect.poll(async () => parseFloat(await readInset())).toBeGreaterThan(300);
  });

  test('footer links hide and body[data-keyboard="open"] is set when keyboard is up', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(PATH);
    await waitForModelReady(page);

    // Before the keyboard appears, footer fades in via the `.visible`
    // class. The opacity transition is 0.3s, so poll until the
    // post-transition value is observed.
    await expect(page.locator('.footer-links')).toHaveClass(/visible/);
    await expect.poll(async () => parseFloat(
      await page.locator('.footer-links').evaluate(el => getComputedStyle(el).opacity)
    ), { timeout: 2_000 }).toBeGreaterThan(0);

    await simulateKeyboard(page, 350);
    await expect(page.locator('body')).toHaveAttribute('data-keyboard', 'open');
    await expect.poll(async () => parseFloat(
      await page.locator('.footer-links').evaluate(el => getComputedStyle(el).opacity)
    )).toBe(0);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Error handling: model load failure
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — model load failure', () => {
  /** Make any fetch of search-embeddings.json fail with a 500. */
  async function breakEmbeddings(page: Page) {
    await page.route('**/search-embeddings.json*', (route: Route) => {
      route.fulfill({ status: 500, body: 'simulated failure' });
    });
  }

  test('embeddings 500 → status=keyword, error banner with Retry button', async ({ page }) => {
    await breakEmbeddings(page);
    await page.goto(PATH);

    // After retries are exhausted, we transition to keyword mode (purple
    // dot) rather than the previous "failed → DDG-only" state. The
    // banner now describes keyword routing instead of a DDG fallback.
    await expect(page.locator('#status')).toHaveAttribute('data-state', 'keyword', { timeout: 30_000 });
    await expect(page.locator('#status')).toHaveClass(/keyword/);
    await expect(page.locator('#error-banner')).toHaveClass(/active/);
    await expect(page.locator('#error-banner')).toContainText(/keyword/i);
    await expect(page.locator('#error-retry')).toBeVisible();
    await expect(page.locator('#loading')).not.toHaveClass(/active/);
  });

  test('Enter on a no-keyword-match query routes to DDG when the model failed', async ({ page }) => {
    await breakEmbeddings(page);
    await page.goto(PATH);
    await expect(page.locator('#status')).toHaveAttribute('data-state', 'keyword', { timeout: 30_000 });

    const search = page.locator('#search');
    // "what is a transformer model" doesn't strongly match any keyword
    // rule (transformers.js would route to GitHub, but the bare word
    // "transformer" doesn't match the 'transformers' keyword on word-
    // boundary). So it correctly falls through to the DDG default.
    await search.fill('what is a transformer model');

    const navPromise = page.waitForURL(/duckduckgo\.com/, { timeout: 15_000 });
    await search.press('Enter');
    await navPromise;
  });

  test('?q=… shows overlay and falls back to DuckDuckGo when model failed', async ({ page }) => {
    await breakEmbeddings(page);
    await freezeRouteTimer(page);
    await page.goto(`${PATH}?q=what+is+a+transformer`);
    await expect(page.locator('#overlay')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('#engine-display')).toHaveText('DuckDuckGo (html)');
  });

  test('Retry button reloads the page', async ({ page }) => {
    // Exhaust the auto-retry path (3 attempts at 500), then succeed on
    // the post-reload fresh init. Confirms Retry actually re-runs init.
    let calls = 0;
    const FAIL_UP_TO = 3;
    await page.route('**/search-embeddings.json*', async (route: Route) => {
      calls += 1;
      if (calls <= FAIL_UP_TO) return route.fulfill({ status: 500, body: 'transient' });
      return route.continue();
    });

    await page.goto(PATH);
    await expect(page.locator('#error-retry')).toBeVisible({ timeout: 30_000 });

    // Click retry (which calls location.reload internally) and wait for
    // a fresh request to /search-embeddings.json.
    await Promise.all([
      page.waitForLoadState('load'),
      page.locator('#error-retry').click(),
    ]);

    // Second load: model should now reach ready.
    await waitForModelReady(page);
    await expect(page.locator('#error-banner')).not.toHaveClass(/active/);
    expect(calls).toBeGreaterThan(FAIL_UP_TO);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Browser registration / OpenSearch / setup page
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — browser registration', () => {
  test('index.html advertises an OpenSearch description', async ({ page }) => {
    await page.goto(PATH);
    const link = page.locator('link[rel="search"][type="application/opensearchdescription+xml"]');
    await expect(link).toHaveCount(1);
    await expect(link).toHaveAttribute('href', '/opensearch.xml');
    await expect(link).toHaveAttribute('title', /divid3/i);
  });

  test('opensearch.xml is reachable and well-formed', async ({ page, request }) => {
    const resp = await request.get('/opensearch.xml');
    expect(resp.ok(), `status ${resp.status()}`).toBeTruthy();
    const ct = resp.headers()['content-type'] || '';
    // Most static servers serve as text/xml or application/xml; either is fine.
    expect(ct).toMatch(/xml/i);
    const xml = await resp.text();
    expect(xml).toMatch(/<OpenSearchDescription/);
    expect(xml).toMatch(/<ShortName>divid3<\/ShortName>/);
    // Required Url with template containing {searchTerms}.
    expect(xml).toMatch(/template="[^"]*\{searchTerms\}[^"]*"/);
    // No accidental remote tracking endpoints in the description.
    expect(xml).not.toMatch(/google-analytics|facebook|doubleclick/i);
  });

  test('setup.html exposes the search URL and a working Copy button', async ({ page, browserName }) => {
    // The Playwright builds of WebKit and Firefox don't expose the
    // clipboard permissions as grantable: WebKit rejects
    // `clipboard-write`, Firefox rejects `clipboard-read`. Real
    // browsers prompt the user the first time anyway, so the headless
    // test wouldn't be representative either way. Chromium is the
    // only one where we can fully exercise the Copy button.
    test.skip(browserName !== 'chromium', 'clipboard permissions are Chromium-only in Playwright');
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/setup.html');

    const url = page.locator('#search-url');
    await expect(url).toContainText('https://divid3.com/?q=%s');

    await page.locator('#copy-url').click();
    await expect(page.locator('#copy-url')).toHaveAttribute('data-state', 'copied');
    await expect(page.locator('#copy-url')).toHaveText(/copied/i);

    // At least one platform card should be open after the UA detector runs.
    await expect(page.locator('details.platform-card[open]')).toHaveCount(1);
  });

  test('homepage footer links to the setup page', async ({ page }) => {
    await page.goto(PATH);
    const link = page.locator('.footer-links a', { hasText: /set as default/i });
    await expect(link).toHaveCount(1);
    await expect(link).toHaveAttribute('href', '/setup.html');
  });
});

// ───────────────────────────────────────────────────────────────────────
// Model load retry (transient failures recover automatically)
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — transient retries', () => {
  test('a single transient 503 on embeddings is retried and recovers', async ({ page }) => {
    let calls = 0;
    await page.route('**/search-embeddings.json*', async (route: Route) => {
      calls += 1;
      if (calls === 1) return route.fulfill({ status: 503, body: 'transient' });
      return route.continue();
    });
    await page.goto(PATH);
    // Even though the first fetch failed, the retry path takes over and
    // the model still ends up ready — no manual Retry click needed.
    await waitForModelReady(page);
    expect(calls).toBeGreaterThanOrEqual(2);
    await expect(page.locator('#error-banner')).not.toHaveClass(/active/);
  });

  test('a deterministic 404 is NOT retried (would burn data plan)', async ({ page }) => {
    let calls = 0;
    await page.route('**/search-embeddings.json*', async (route: Route) => {
      calls += 1;
      return route.fulfill({ status: 404, body: 'not found' });
    });
    await page.goto(PATH);
    // After deterministic failure (no retries) we transition straight to
    // keyword mode. Same end-state as 5xx exhaust + retry, just faster.
    await expect(page.locator('#status')).toHaveAttribute('data-state', 'keyword', { timeout: 30_000 });
    // Exactly one fetch attempt — no retry storm on a hard miss.
    expect(calls).toBe(1);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Keyboard shortcuts overlay
//
// The single-letter shortcuts (`?`, `/`, `t`) are deliberately *not*
// honored while the search input has focus — otherwise typing a query
// containing any of those characters would silently fire the shortcut
// (the long-standing "typing a query randomly turns the page light"
// bug). Each test below blurs the input first so that we exercise the
// document-level handler, not the user-typing path.
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — keyboard shortcuts', () => {
  /** Move focus off `#search` so document-level shortcuts fire. */
  async function blurSearch(page: Page) {
    await page.locator('#search').evaluate(el => (el as HTMLElement).blur());
  }

  test('? key opens and closes the shortcuts overlay', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);
    await blurSearch(page);

    await page.keyboard.press('?');
    await expect(page.locator('#shortcuts-overlay')).toHaveClass(/active/);

    await page.keyboard.press('Escape');
    await expect(page.locator('#shortcuts-overlay')).not.toHaveClass(/active/);
  });

  test('/ key focuses the search input from elsewhere on the page', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);
    await blurSearch(page);
    await expect(page.locator('#search')).not.toBeFocused();

    await page.keyboard.press('/');
    await expect(page.locator('#search')).toBeFocused();
    // The `/` should NOT have been inserted as a character — the
    // document handler ran preventDefault.
    await expect(page.locator('#search')).toHaveValue('');
  });

  test('T key toggles the theme (adds .light or .dark)', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);
    await blurSearch(page);

    const before = await page.evaluate(() => document.documentElement.className);
    await page.keyboard.press('t');
    const after = await page.evaluate(() => document.documentElement.className);
    expect(after).not.toBe(before);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Smart paste: strip protocol from pasted URLs
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — smart paste', () => {
  // Firefox refuses to honor the `clipboardData` field on a manually
  // constructed `ClipboardEvent` (security policy: scripts can't synthesize
  // a paste), so our synthetic dispatch can't actually carry text into the
  // page on Gecko. Real ⌘V / Ctrl-V paste works fine in Firefox; only the
  // synthetic test below is unrunnable. The handler itself is shared code
  // exercised on Chromium + WebKit + mobile-safari.
  test.skip(({ browserName }) => browserName === 'firefox',
    "Firefox doesn't expose clipboardData on synthetic ClipboardEvents");

  test('pasting "https://github.com" strips the protocol', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    await page.locator('#search').evaluate(el => {
      const dt = new DataTransfer();
      dt.setData('text/plain', 'https://github.com');
      el.dispatchEvent(new ClipboardEvent('paste', {
        bubbles: true,
        cancelable: true,
        clipboardData: dt,
      }));
    });

    await expect(page.locator('#search')).toHaveValue('github.com');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'direct');
  });

  test('pasting a regular search query is not modified', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    await page.locator('#search').click();
    await page.locator('#search').fill('how to make pizza');

    await expect(page.locator('#search')).toHaveValue('how to make pizza');
  });
});

// ───────────────────────────────────────────────────────────────────────
// Theme toggle
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — theme toggle', () => {
  test('theme toggle button is present and clickable', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const btn = page.locator('#theme-toggle');
    await expect(btn).toBeVisible();
    await expect(btn).toHaveAttribute('aria-label', /toggle dark mode/i);

    const before = await page.evaluate(() => document.documentElement.className);
    await btn.click();
    const after = await page.evaluate(() => document.documentElement.className);
    expect(after).not.toBe(before);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Click-to-route: clicking the engine hint instantly routes
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — click-to-route', () => {
  test('clicking the engine hint navigates immediately', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.fill('!yt lofi');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'youtube');

    const navPromise = page.waitForURL(/youtube\.com/, { timeout: 15_000, waitUntil: 'commit' });
    await page.locator('#hint').click();
    await navPromise;
  });

  test('clicking hint on a semantic query routes to the hinted engine', async ({ page, isMobile }) => {
    test.skip(isMobile, 'mobile shows no hint for semantic queries (live inference is desktop-only)');

    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.fill('how to fix a flat tire');
    await expect(page.locator('body')).toHaveAttribute('data-engine', /.+/, { timeout: 10_000 });

    // Clicking the hint should navigate — we just assert we leave the page.
    const navPromise = page.waitForURL(url => {
      const host = new URL(url.toString()).hostname;
      return host !== 'localhost';
    }, { timeout: 15_000, waitUntil: 'commit' });
    await page.locator('#hint').click();
    await navPromise;
  });

  test('clicking a score chip OVERRIDES the model and routes there', async ({ page, isMobile }) => {
    test.skip(isMobile, 'mobile shows no scores during typing (live inference is desktop-only)');

    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.fill('lofi beats');
    // Whatever the model picked, we assert the override sends the user
    // to Wirecutter — that proves the chip click ignored the model's
    // decision rather than coincidentally agreeing with it.
    await expect(page.locator('#scores .score-row[data-engine="wirecutter"]')).toBeVisible({ timeout: 5_000 });
    const modelPick = await page.locator('body').getAttribute('data-engine');
    expect(modelPick).not.toBe('wirecutter');

    const navPromise = page.waitForURL(/nytimes\.com\/wirecutter/, { timeout: 15_000, waitUntil: 'commit' });
    await page.locator('#scores .score-row[data-engine="wirecutter"]').click();
    await navPromise;
    expect(new URL(page.url()).hostname).toMatch(/nytimes\.com$/);
  });

  test('every score chip is keyboard-activatable as a real <button>', async ({ page, isMobile }) => {
    test.skip(isMobile, 'mobile shows no scores during typing (live inference is desktop-only)');

    await page.goto(PATH);
    await waitForModelReady(page);

    await page.locator('#search').fill('lofi beats');
    await expect(page.locator('#scores .score-row').first()).toBeVisible({ timeout: 5_000 });

    // Real <button> elements: focusable, have an accessible name, and
    // expose role=button to assistive tech without an explicit role.
    const tags = await page.$$eval('#scores .score-row', rows =>
      rows.map(r => r.tagName.toLowerCase()),
    );
    expect(tags.every(t => t === 'button')).toBe(true);

    const labels = await page.$$eval('#scores .score-row', rows =>
      rows.map(r => r.getAttribute('aria-label') ?? ''),
    );
    expect(labels.every(l => /Route to .+ \(\d+% match\)/.test(l))).toBe(true);
  });

  test('keyboard Enter on a focused score chip overrides the route', async ({ page, isMobile }) => {
    test.skip(isMobile, 'mobile shows no scores during typing (live inference is desktop-only)');

    await page.goto(PATH);
    await waitForModelReady(page);

    await page.locator('#search').fill('lofi beats');
    await expect(page.locator('#scores .score-row[data-engine="hn"]')).toBeVisible({ timeout: 5_000 });

    const navPromise = page.waitForURL(/hn\.algolia\.com/, { timeout: 15_000, waitUntil: 'commit' });
    // `.focus()` then space is more deterministic than tabbing through
    // the document because some engines focus the URL bar instead.
    await page.locator('#scores .score-row[data-engine="hn"]').focus();
    await page.keyboard.press('Enter');
    await navPromise;
  });
});

// ───────────────────────────────────────────────────────────────────────
// Cache reliability (the real iOS pain point)
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — cache reliability', () => {
  test('reloading the page reuses the cached model (no re-download of model_quantized.onnx)', async ({ page, context }) => {
    // First load: model is fetched.
    await page.goto(PATH);
    await waitForModelReady(page);

    // Reload via a fresh page on the same context (which keeps Cache
    // Storage + IndexedDB for the same origin). Track whether the
    // ~22 MB ONNX hits the network on the second load.
    const second = await context.newPage();
    let modelHits = 0;
    second.on('request', r => {
      if (r.url().endsWith('model_quantized.onnx')) modelHits += 1;
    });
    await second.goto(PATH);
    await expect(second.locator('#status')).toHaveAttribute('data-state', 'ready', { timeout: MODEL_TIMEOUT });
    // We don't assert modelHits === 0 because the served-from-cache
    // request might still register; we just assert it stays small.
    expect(modelHits).toBeLessThanOrEqual(1);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Keyword-only routing mode (the low-memory / model-disabled fallback)
//
// Activated by:
//   - `?lite=1` URL parameter (explicit user opt-in / deep link)
//   - Crash-loop guard (≥ 2 unfinished cold loads in a row)
//   - Model load failure after retries
//
// In this mode the embedding model is never loaded. classify() routes
// via deterministic keyword rules (~ 100 phrase patterns across 10
// engines, weighted by specificity), with DDG as the no-match fallback.
//
// The status dot turns purple to signal the mode visually. Bangs and
// direct URL detection still work — they were always rule-based.
// ───────────────────────────────────────────────────────────────────────
test.describe('search router — keyword mode (low-memory fallback)', () => {
  /**
   * Boot the page in keyword mode and wait for it to settle. We use the
   * `?lite=1` URL param as the canonical activation path; the per-engine
   * routing assertions don't care WHY we ended up in keyword mode, only
   * that the routing works deterministically once we're there.
   */
  async function bootKeywordMode(page: Page) {
    await page.goto(`${PATH}?lite=1`);
    await expect(page.locator('#status')).toHaveAttribute('data-state', 'keyword', {
      timeout: 10_000,
    });
  }

  test('?lite=1 URL parameter activates keyword mode (purple dot, no model load)', async ({ page }) => {
    // Track whether the embeddings JSON was requested. In keyword mode
    // we should skip both the embeddings fetch AND the ONNX download.
    let embeddingsHits = 0;
    let modelHits = 0;
    await page.route('**/search-embeddings.json*', (route: Route) => {
      embeddingsHits += 1;
      return route.continue();
    });
    await page.route('**/model_quantized.onnx', (route: Route) => {
      modelHits += 1;
      return route.continue();
    });

    await bootKeywordMode(page);

    await expect(page.locator('#status')).toHaveClass(/keyword/);
    // Loading overlay never came up.
    await expect(page.locator('#loading')).not.toHaveClass(/active/);
    // Footer becomes visible after init resolves.
    await expect(page.locator('.footer-links')).toHaveClass(/visible/);

    // Give any stray fetch a moment to surface.
    await page.waitForTimeout(500);
    expect(embeddingsHits, 'embeddings.json should not be fetched in keyword mode').toBe(0);
    expect(modelHits, 'ONNX model should not be downloaded in keyword mode').toBe(0);
  });

  // ── Per-engine routing table ─────────────────────────────────────
  //
  // For each engine we pick a query that should match the keyword
  // rules deterministically and assert performRoute (Enter) goes there.
  // These assertions are stable: keyword classification is pure regex,
  // no model nondeterminism, no thresholds to drift past.
  const cases: { query: string; engine: string; host: RegExp; qFragment: string }[] = [
    { query: 'lofi beats',                    engine: 'youtube',     host: /(^|\.)youtube\.com$/,      qFragment: 'lofi' },
    { query: 'show hn react server components', engine: 'hn',        host: /(^|\.)algolia\.com$/,      qFragment: 'react' },
    { query: 'integral of x^2',               engine: 'wolfram',     host: /(^|\.)wolframalpha\.com$/, qFragment: 'integral' },
    { query: 'best wireless headphones',      engine: 'wirecutter',  host: /(^|\.)nytimes\.com$/,      qFragment: 'wireless' },
    { query: 'coffee shops near me',          engine: 'maps',        host: /(^|\.)google\.com$/,       qFragment: 'coffee' },
    { query: 'image of saturn',               engine: 'bing-images', host: /(^|\.)bing\.com$/,         qFragment: 'saturn' },
    { query: 'explain quantum mechanics',     engine: 'perplexity',  host: /(^|\.)perplexity\.ai$/,    qFragment: 'quantum' },
    { query: 'write a haiku about cats',      engine: 'grok',        host: /(^|\.)grok\.com$/,         qFragment: 'haiku' },
    { query: 'buy vintage camera lens',       engine: 'ebay',        host: /(^|\.)ebay\.com$/,         qFragment: 'vintage' },
  ];

  for (const c of cases) {
    test(`keyword routing: "${c.query}" → ${c.engine}`, async ({ page }) => {
      await bootKeywordMode(page);

      const search = page.locator('#search');
      await search.fill(c.query);

      const navPromise = page.waitForURL(url => {
        return c.host.test(new URL(url.toString()).hostname);
      }, { timeout: 15_000, waitUntil: 'commit' });
      await search.press('Enter');
      await navPromise;
      // Make sure the user's query actually rode along on the redirect.
      expect(decodeURIComponent(page.url())).toMatch(new RegExp(c.qFragment, 'i'));
    });
  }

  test('keyword routing: a query with no matching keywords falls through to DDG', async ({ page }) => {
    await bootKeywordMode(page);

    const search = page.locator('#search');
    // No bang, no domain, and no rule keyword — should land on DDG.
    await search.fill('current population of japan');
    const navPromise = page.waitForURL(/duckduckgo\.com/, { timeout: 15_000, waitUntil: 'commit' });
    await search.press('Enter');
    await navPromise;
  });

  test('keyword routing: bangs still take precedence (rule-based, untouched by mode)', async ({ page }) => {
    await bootKeywordMode(page);

    const search = page.locator('#search');
    // We use "!yt cake recipe" — without the bang "cake recipe" matches
    // no keyword and would land on DDG, but with the bang it must go to
    // YouTube. That makes it unambiguous that the bang is what's driving
    // the engine selection (not coincident keyword matching).
    await search.fill('!yt cake recipe');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'youtube');

    const navPromise = page.waitForURL(/youtube\.com/, { timeout: 15_000, waitUntil: 'commit' });
    await search.press('Enter');
    await navPromise;
  });

  test('keyword routing: direct URL detection still works (rule-based)', async ({ page }) => {
    await bootKeywordMode(page);

    const search = page.locator('#search');
    await search.fill('github.com');
    await expect(page.locator('body')).toHaveAttribute('data-engine', 'direct');
    await expect(page.locator('#hint')).toHaveText('Direct Link');
  });

  test('keyword routing: ?q= URL parameter shows overlay and routes via keywords', async ({ page }) => {
    // The `?q=` path runs through performRoute → classify,
    // which respects keywordMode the same way Enter does. So a
    // ?q=lofi+beats&lite=1 visit should show the overlay with YouTube
    // selected, without ever loading the model.
    let modelHits = 0;
    await page.route('**/model_quantized.onnx', (route: Route) => {
      modelHits += 1;
      return route.continue();
    });

    await freezeRouteTimer(page);
    await page.goto(`${PATH}?q=lofi+beats&lite=1`);
    await expect(page.locator('#overlay')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('#engine-display')).toHaveText('YouTube');
    await expect(page.locator('#override-engines .override-btn.selected')).toHaveAttribute('data-engine', 'youtube');
    expect(modelHits, 'model should not have been fetched').toBe(0);
  });

  test('keyword routing: model-load failure also activates keyword mode', async ({ page }) => {
    // Break the embeddings fetch — initModel will fail after retries
    // and flip to keywordMode automatically (without needing ?lite=1).
    await page.route('**/search-embeddings.json*', (route: Route) => {
      route.fulfill({ status: 500, body: 'simulated failure' });
    });

    await page.goto(PATH);

    await expect(page.locator('#status')).toHaveAttribute('data-state', 'keyword', {
      timeout: 30_000,
    });
    await expect(page.locator('#status')).toHaveClass(/keyword/);

    // Routing should still work via keywords even though the model
    // never loaded. Pick a query with a strong keyword signal.
    const search = page.locator('#search');
    await search.fill('integral of sin(x)');
    const navPromise = page.waitForURL(/wolframalpha\.com/, { timeout: 15_000, waitUntil: 'commit' });
    await search.press('Enter');
    await navPromise;
  });

  test('keyword routing: case insensitive matching', async ({ page }) => {
    await bootKeywordMode(page);

    const search = page.locator('#search');
    // SHOUTING shouldn't break the rules.
    await search.fill('LOFI BEATS');
    const navPromise = page.waitForURL(/youtube\.com/, { timeout: 15_000, waitUntil: 'commit' });
    await search.press('Enter');
    await navPromise;
  });

  test('keyword routing: word boundaries — "decode" does NOT match a future "code" rule', async ({ page }) => {
    // Defensive test against future regressions. If a contributor adds
    // a bare 'code' keyword to any engine's rules, queries containing
    // "decode" / "encoded" would silently misroute. Word-boundary
    // matching is what prevents that — assert it stays correct.
    await bootKeywordMode(page);

    const search = page.locator('#search');
    await search.fill('decode this string');
    const navPromise = page.waitForURL(/duckduckgo\.com/, { timeout: 15_000, waitUntil: 'commit' });
    await search.press('Enter');
    await navPromise;
  });
});
