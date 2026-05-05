import { test, expect, Page } from '@playwright/test';

/**
 * Mobile + WebKit-specific regression tests.
 *
 * These tests exist because the desktop-Chromium suite has historically
 * been blind to:
 *
 *   1. The "typing 't' silently flips theme to light" bug (a keydown
 *      handler attached directly to the search input was preventing
 *      default and toggling theme for every `t` typed, plus eating
 *      `?` and `/` characters).
 *
 *   2. Mobile bottom-of-viewport collisions: the scores panel was a
 *      fixed-bottom horizontal-scroll strip stacked under the footer
 *      ("Privacy", "Source") with only ~0.5rem of breathing room. With
 *      the soft keyboard up, the two layers overlapped visually.
 *
 *   3. iOS Safari "A problem repeatedly occurred" — the WebContent
 *      process gets killed (typically OOM during model load), iOS
 *      blacklists the URL after ~3 crashes. We now detect the
 *      crash-loop via a session-storage sentinel and short-circuit to
 *      a rule-based "lite mode" so the tab stops crashing.
 *
 * Most of these tests run under `webkit` and `mobile-safari` projects
 * to catch regressions on the engine our users actually run.
 */

const PATH = '/index.html';
const MODEL_TIMEOUT = 60_000;

async function waitForModelReady(page: Page) {
  await expect(page.locator('#status')).toHaveAttribute(
    'data-state', 'ready', { timeout: MODEL_TIMEOUT },
  );
}

// ───────────────────────────────────────────────────────────────────────
// Theme: the 't'-while-typing bug
// ───────────────────────────────────────────────────────────────────────
test.describe('theme stability while typing', () => {
  test('typing a query containing "t" does NOT toggle the theme', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const html = page.locator('html');
    const initialIsLight = await html.evaluate(el => el.classList.contains('light'));

    const search = page.locator('#search');
    await search.click();
    // Type something with several `t`s, plus `/` and `?` which were
    // also being intercepted by the same buggy handler.
    await search.pressSequentially('test things ?');

    // The query should be in the input as typed — including every `t`.
    await expect(search).toHaveValue('test things ?');

    // And the theme must not have changed underneath us.
    const finalIsLight = await html.evaluate(el => el.classList.contains('light'));
    expect(finalIsLight).toBe(initialIsLight);
  });

  test('"/" typed in the search field is captured as a query character, not a focus shortcut', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.click();
    await search.pressSequentially('a/b');
    await expect(search).toHaveValue('a/b');
  });

  test('"?" typed in the search field does NOT pop the shortcuts overlay', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.click();
    await search.pressSequentially('why?');

    await expect(search).toHaveValue('why?');
    await expect(page.locator('#shortcuts-overlay')).not.toHaveClass(/active/);
  });

  test('the keyboard shortcut still works when focus is NOT in the search input', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const html = page.locator('html');
    const initialIsLight = await html.evaluate(el => el.classList.contains('light'));

    // Move focus off the input and press T at the document level.
    await page.locator('#search').evaluate(el => (el as HTMLElement).blur());
    await page.keyboard.press('t');

    const afterIsLight = await html.evaluate(el => el.classList.contains('light'));
    expect(afterIsLight).toBe(!initialIsLight);
  });

  test('toggling theme also updates the iOS theme-color meta tag', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const meta = page.locator('meta#theme-color');
    const button = page.locator('#theme-toggle');

    await button.click();
    const c1 = await meta.getAttribute('content');
    await button.click();
    const c2 = await meta.getAttribute('content');

    expect([c1, c2].sort()).toEqual(['#000000', '#ffffff']);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Mobile layout: scores must not overlap the footer / status dot
// ───────────────────────────────────────────────────────────────────────
test.describe('mobile layout — scores panel placement', () => {
  test('scores panel renders inline beneath the input on mobile', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'mobile-only layout invariant');

    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.click();
    await search.pressSequentially('youtube videos');
    await expect(page.locator('#scores .score-row').first()).toBeVisible({ timeout: 5_000 });

    // Inline placement: the scores panel should live inside .input-wrap.
    const insideWrap = await page.locator('#scores').evaluate(el => {
      return !!el.closest('.input-wrap');
    });
    expect(insideWrap).toBe(true);

    // And its computed `position` should be `static` (the inline default).
    const position = await page.locator('#scores').evaluate(el =>
      getComputedStyle(el).position,
    );
    expect(position).toBe('static');
  });

  test('scores panel does not overlap any footer link', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.click();
    await search.pressSequentially('youtube videos');
    await expect(page.locator('#scores .score-row').first()).toBeVisible({ timeout: 5_000 });

    const scoresBox = await page.locator('#scores').boundingBox();
    expect(scoresBox).not.toBeNull();

    const footerEl = page.locator('.footer-links');
    const footerVisible = await footerEl.evaluate(el =>
      getComputedStyle(el).opacity !== '0' && getComputedStyle(el).visibility !== 'hidden',
    );
    if (!footerVisible) return;

    // The container `.footer-links` is `left: 0; right: 0` for centering
    // and so reports a full-width bounding box, but the visible content
    // is just three centered links. Asserting against the container
    // would false-positive on desktop where the bottom-left scores
    // panel shares the same Y band with the empty left half of the
    // footer container. Check each <a> individually instead.
    const links = page.locator('.footer-links a');
    const count = await links.count();
    for (let i = 0; i < count; i++) {
      const linkBox = await links.nth(i).boundingBox();
      if (!linkBox) continue;
      const overlapX =
        Math.min(scoresBox!.x + scoresBox!.width, linkBox.x + linkBox.width) -
        Math.max(scoresBox!.x, linkBox.x);
      const overlapY =
        Math.min(scoresBox!.y + scoresBox!.height, linkBox.y + linkBox.height) -
        Math.max(scoresBox!.y, linkBox.y);
      expect(
        overlapX <= 0 || overlapY <= 0,
        `scores ${JSON.stringify(scoresBox)} overlaps link[${i}] ${JSON.stringify(linkBox)}`,
      ).toBe(true);
    }
  });

  test('scores panel does not overlap the status dot rectangle', async ({ page }) => {
    await page.goto(PATH);
    await waitForModelReady(page);

    const search = page.locator('#search');
    await search.click();
    await search.pressSequentially('youtube videos');
    await expect(page.locator('#scores .score-row').first()).toBeVisible({ timeout: 5_000 });

    const scoresBox = await page.locator('#scores').boundingBox();
    const dotBox = await page.locator('#status').boundingBox();
    expect(scoresBox).not.toBeNull();
    expect(dotBox).not.toBeNull();

    const overlapX = Math.min(scoresBox!.x + scoresBox!.width, dotBox!.x + dotBox!.width) -
                     Math.max(scoresBox!.x, dotBox!.x);
    const overlapY = Math.min(scoresBox!.y + scoresBox!.height, dotBox!.y + dotBox!.height) -
                     Math.max(scoresBox!.y, dotBox!.y);
    // No 2D intersection.
    expect(overlapX <= 0 || overlapY <= 0).toBe(true);
  });

  test('footer hides when keyboard inset is present (mobile only)', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'mobile-only — desktop has no concept of soft keyboard');
    await page.goto(PATH);
    await waitForModelReady(page);

    // Simulate the visualViewport shrinking. There is no programmatic
    // way to raise the iOS soft keyboard from Playwright, so we set
    // the data attribute the CSS keys off of.
    await page.evaluate(() => {
      document.body.dataset.keyboard = 'open';
    });

    // The footer-links has a 0.3s opacity transition, so poll until
    // the fade-out completes (or we time out).
    await expect.poll(async () => parseFloat(
      await page.locator('.footer-links').evaluate(el => getComputedStyle(el).opacity),
    ), { timeout: 2_000 }).toBeLessThan(0.01);
  });
});

// ───────────────────────────────────────────────────────────────────────
// Crash-loop guard
// ───────────────────────────────────────────────────────────────────────
test.describe('iOS crash-loop guard', () => {
  test('boot after two unfinished loads enters lite mode and shows banner', async ({ page }) => {
    // Pre-seed sessionStorage as if the previous load crashed once and
    // another attempt is still "in progress" — that's exactly the state
    // the page would find itself in after iOS killed an earlier tab.
    // The boot sequence will detect the in-progress flag, increment to
    // 2, and short-circuit into lite mode.
    await page.addInitScript(() => {
      sessionStorage.setItem('divid3-crash-count', '1');
      sessionStorage.setItem('divid3-loading', '1');
    });

    await page.goto(PATH);

    await expect(page.locator('#status')).toHaveAttribute('data-state', 'failed', {
      timeout: 10_000,
    });
    await expect(page.locator('#error-banner')).toHaveClass(/active/);

    // Bangs and Enter still work — verify by typing a bang.
    const search = page.locator('#search');
    await search.click();
    await search.pressSequentially('!yt cats');
    await expect(page.locator('#hint')).toHaveText('YouTube', { timeout: 5_000 });
  });

  test('successful model load resets the crash counter', async ({ page }) => {
    // Pre-seed a non-zero crash count without the in-progress flag, so
    // initModel proceeds normally and should clear the counter on success.
    await page.addInitScript(() => {
      sessionStorage.setItem('divid3-crash-count', '1');
    });

    await page.goto(PATH);
    await expect(page.locator('#status')).toHaveAttribute('data-state', 'ready', {
      timeout: MODEL_TIMEOUT,
    });

    const count = await page.evaluate(() => sessionStorage.getItem('divid3-crash-count'));
    expect(count).toBe('0');
  });

  test('the "loading" sentinel is cleared on successful boot', async ({ page }) => {
    await page.goto(PATH);
    await expect(page.locator('#status')).toHaveAttribute('data-state', 'ready', {
      timeout: MODEL_TIMEOUT,
    });

    const flag = await page.evaluate(() => sessionStorage.getItem('divid3-loading'));
    expect(flag).toBeNull();
  });
});

// ───────────────────────────────────────────────────────────────────────
// Sanity: no console errors / pageerrors on a clean WebKit boot
// ───────────────────────────────────────────────────────────────────────
test('clean boot — no console errors', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));
  await page.goto(PATH);
  await expect(page.locator('#status')).toHaveAttribute('data-state', 'ready', {
    timeout: MODEL_TIMEOUT,
  });
  // Filter out network-level noise + benign WebKit warnings that
  // aren't app bugs:
  //   - "Failed to load resource" (CDN noise);
  //   - "Viewport argument key 'interactive-widget' not recognized" —
  //     WebKit doesn't yet implement `interactive-widget=resizes-content`
  //     and warns once on boot. We deliberately keep the directive
  //     because Chromium honors it; WebKit ignores it harmlessly.
  const real = errors.filter(e =>
    !/Failed to load resource/i.test(e) &&
    !/interactive-widget/i.test(e)
  );
  expect(real, `unexpected errors:\n${real.join('\n')}`).toEqual([]);
});
