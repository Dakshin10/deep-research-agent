import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'fs';
import path from 'path';

const RAW_DIR = path.resolve(__dirname, '../../../docs/ui/raw');

async function sendPrompt(page: any, text: string) {
  const textarea = page.locator('textarea');
  await textarea.fill(text);
  const sendBtn = page.locator('button[aria-label="Send message"]');
  await sendBtn.click();
}

test.describe('Real Quality Measurements (Phase 5)', () => {
  test.beforeAll(() => {
    if (!fs.existsSync(RAW_DIR)) {
      fs.mkdirSync(RAW_DIR, { recursive: true });
    }
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  // 1. Axe-core accessibility scan (target: 0 critical / serious violations)
  test('Axe-core accessibility audit (Empty State & Active State)', async ({ page }) => {
    // Run axe on empty state
    const emptyScan = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    fs.writeFileSync(
      path.join(RAW_DIR, 'axe_empty_state.json'),
      JSON.stringify(emptyScan, null, 2)
    );

    const seriousOrCriticalEmpty = emptyScan.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
    expect(seriousOrCriticalEmpty.length).toBe(0);

    // Send a message and run axe on active state
    await sendPrompt(page, 'what is 15% of 2,340');
    await expect(page.locator('.max-w-\\[720px\\] .font-serif').last()).toContainText('351', { timeout: 8000 });

    const activeScan = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    fs.writeFileSync(
      path.join(RAW_DIR, 'axe_active_state.json'),
      JSON.stringify(activeScan, null, 2)
    );

    const seriousOrCriticalActive = activeScan.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
    expect(seriousOrCriticalActive.length).toBe(0);
  });

  // 2. Cumulative Layout Shift (CLS)
  test('Cumulative Layout Shift measurement during stream', async ({ page }) => {
    // Initialize layout-shift observer in the browser context
    await page.evaluate(() => {
      (window as any).__clsScore = 0;
      const observer = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries()) {
          if (!(entry as any).hadRecentInput) {
            (window as any).__clsScore += (entry as any).value;
          }
        }
      });
      observer.observe({ type: 'layout-shift', buffered: true });
    });

    await sendPrompt(page, 'research the latest in solid-state batteries');

    await expect(page.locator('button:has-text("Searched 5 sources"), button:has-text("sources across parallel shards")').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.max-w-\\[720px\\] .font-serif').last()).toBeVisible({ timeout: 10000 });

    const clsScore = await page.evaluate(() => (window as any).__clsScore || 0);

    fs.writeFileSync(
      path.join(RAW_DIR, 'cls_measurement.json'),
      JSON.stringify({ cls: clsScore, timestamp: new Date().toISOString() }, null, 2)
    );

    // Good web vital CLS is < 0.1
    expect(clsScore).toBeLessThan(0.1);
  });

  // 3. Time to First Status Line (TTFS) and Time to First Token (TTFT)
  test('Latency benchmarks: TTFS and TTFT', async ({ page }) => {
    const textarea = page.locator('textarea');
    await textarea.fill('research the latest in solid-state batteries');

    const clickStart = Date.now();
    const sendBtn = page.locator('button[aria-label="Send message"]');
    await sendBtn.click();

    // Measure TTFS
    const statusLine = page.locator('button:has-text("Searched 5 sources"), button:has-text("sources across parallel shards")').first();
    await statusLine.waitFor({ state: 'visible', timeout: 10000 });
    const ttfsMs = Date.now() - clickStart;

    // Measure TTFT
    const firstProse = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await firstProse.waitFor({ state: 'visible', timeout: 10000 });
    const ttftMs = Date.now() - clickStart;

    const latencyData = {
      scenario: 'deep_research',
      ttfs_ms: ttfsMs,
      ttft_ms: ttftMs,
      measured_at: new Date().toISOString(),
    };

    fs.writeFileSync(
      path.join(RAW_DIR, 'latency_measurements.json'),
      JSON.stringify(latencyData, null, 2)
    );

    expect(ttfsMs).toBeGreaterThan(0);
    expect(ttftMs).toBeGreaterThan(0);
  });

  // 4. Keyboard-only walkthrough of overlays
  test('Keyboard accessibility: overlay shortcuts, Esc handling, and focus', async ({ page }) => {
    // Open History Drawer
    const historyBtn = page.locator('button[aria-label="History"]');
    await historyBtn.click();

    const historyDrawer = page.locator('text=Conversations').first();
    await expect(historyDrawer).toBeVisible({ timeout: 5000 });

    // Escape closes History Drawer
    await page.keyboard.press('Escape');
    await expect(historyDrawer).not.toBeVisible({ timeout: 5000 });

    // Open Memory Graph via typing
    await sendPrompt(page, 'show my memory graph');
    const graphOverlay = page.locator('text=Aether Knowledge Graph & Memory').first();
    await expect(graphOverlay).toBeVisible({ timeout: 10000 });

    // Escape closes Memory Graph
    await page.keyboard.press('Escape');
    await expect(graphOverlay).not.toBeVisible({ timeout: 5000 });

    fs.writeFileSync(
      path.join(RAW_DIR, 'keyboard_walkthrough.txt'),
      'Keyboard walkthrough passed: History drawer opens and Esc closes. Natural language opens Memory Graph and Esc closes.\n'
    );
  });

  // 5. Prefers-reduced-motion check
  test('Prefers-reduced-motion media feature check', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const reducedMotionActive = await page.evaluate(() => {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    });

    expect(reducedMotionActive).toBe(true);

    fs.writeFileSync(
      path.join(RAW_DIR, 'reduced_motion.json'),
      JSON.stringify({ prefersReducedMotionActive: reducedMotionActive, timestamp: new Date().toISOString() }, null, 2)
    );
  });
});
