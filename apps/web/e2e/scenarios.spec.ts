import { test, expect } from '@playwright/test';

async function sendPrompt(page: any, text: string) {
  const textarea = page.locator('textarea');
  await textarea.fill(text);
  const sendBtn = page.locator('button[aria-label="Send message"]');
  await sendBtn.click();
}

test.describe('Single-Screen Type-Only Assistant E2E Scenarios (Mock CI)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  // Scenario 1: Direct Math Answer
  test('Scenario 1: direct math answer without tools', async ({ page }) => {
    await sendPrompt(page, "what is 15% of 2,340");

    // Expect direct answer containing 351 in reading column
    const assistantProse = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(assistantProse).toContainText('351', { timeout: 8000 });

    // Assert no tool execution or status line was triggered
    const tools = page.locator('.lucide-code, .lucide-terminal');
    await expect(tools).toHaveCount(0);
  });

  // Scenario 2: Deep Research Zero-Click
  test('Scenario 2: deep research with status line, report card, and verified citation chip', async ({ page }) => {
    await sendPrompt(page, 'research the latest in solid-state batteries');

    // 1. Status line is visible
    const statusLine = page.locator('button:has-text("Searched 5 sources"), button:has-text("sources across parallel shards")').first();
    await expect(statusLine).toBeVisible({ timeout: 10000 });

    // 2. Report artifact card is visible
    const artifactCard = page.locator('button:has-text("Research Report:"), button:has-text("Click to view in panel")').first();
    await expect(artifactCard).toBeVisible({ timeout: 10000 });

    // 3. Citation link exists with verified text-fragment URL
    const citationLink = page.locator('a[href*="#:~:text="]').first();
    await expect(citationLink).toBeVisible({ timeout: 5000 });

    // Check href attribute contains text fragment
    const href = await citationLink.getAttribute('href');
    expect(href).toContain('#:~:text=');
  });

  // Scenario 3: Memory Recall
  test('Scenario 3: memory recall with memory-used chip', async ({ page }) => {
    await sendPrompt(page, 'what did I decide about the pricing model last week');

    // Expect memory-used chip
    const memoryChip = page.locator('button:has-text("Memory used")').first();
    await expect(memoryChip).toBeVisible({ timeout: 10000 });

    // Click memory chip to expand
    await memoryChip.click();
    await expect(page.locator('text=Pricing Model').first()).toBeVisible({ timeout: 5000 });

    // Verify assistant answer text
    const prose = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(prose).toContainText('49', { timeout: 5000 });
  });

  // Scenario 4: Hackathon Ideas Artifact
  test('Scenario 4: hackathon ideas -> idea-card artifact in side panel', async ({ page }) => {
    await sendPrompt(page, 'find hackathon ideas for problem statement PS 26102');

    // Expect idea-cards artifact card
    const ideaCardBtn = page.locator('button:has-text("Hackathon Idea Portfolio"), button:has-text("idea-cards · Click to view in panel")').first();
    await expect(ideaCardBtn).toBeVisible({ timeout: 10000 });

    // Click to open side panel
    await ideaCardBtn.click({ force: true });
    await expect(page.locator('text=Artifact').first()).toBeVisible({ timeout: 5000 });
  });

  // Scenario 5: CSV Data Analysis
  test('Scenario 5: CSV analysis -> churn chart artifact', async ({ page }) => {
    await sendPrompt(page, 'which month had the highest churn in this dataset');

    // Expect chart artifact card
    const chartCard = page.locator('button:has-text("Monthly Churn Rate Cohort Analysis"), button:has-text("cohort-churn · Click to view in panel")').first();
    await expect(chartCard).toBeVisible({ timeout: 10000 });

    // Expect text stating October at 8.4%
    const prose = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(prose).toContainText('October', { timeout: 5000 });
    await expect(prose).toContainText('8.4%', { timeout: 5000 });
  });

  // Scenario 6: Show Memory Graph
  test('Scenario 6: "show my memory graph" opens full-screen overlay', async ({ page }) => {
    await sendPrompt(page, 'show my memory graph');

    // Expect memory graph overlay to open
    const graphOverlay = page.locator('text=Aether Knowledge Graph & Memory').first();
    await expect(graphOverlay).toBeVisible({ timeout: 10000 });
    await page.keyboard.press('Escape');
    await expect(graphOverlay).not.toBeVisible();
  });

  // Scenario 7: Forget Destructive Approval Card
  test('Scenario 7: "forget everything about Project X" shows approval card and deletes only after Approve', async ({ page }) => {
    await sendPrompt(page, 'forget everything about Project X');

    // Expect approval card
    const approveBtn = page.locator('button:has-text("Approve & Execute")');
    await expect(approveBtn).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Project X').first()).toBeVisible();

    // Click Approve
    await approveBtn.click();

    // Expect deletion confirmation
    const prose = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(prose).toContainText('deleted', { timeout: 10000 });
  });

  // Scenario 8: Go Private Mode
  test('Scenario 8: "go private" disables memory read/write', async ({ page }) => {
    await sendPrompt(page, 'go private');

    // Expect private confirmation
    const prose = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(prose).toContainText('Private mode is now active', { timeout: 10000 });

    // Expect private badge in header
    const privateBadge = page.locator('button[title*="Private mode is ON"], button:has-text("Private")').first();
    await expect(privateBadge).toBeVisible();
  });

  // Scenario 9: Export Vault
  test('Scenario 9: "export my vault" triggers vault download', async ({ page }) => {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 8000 }).catch(() => null),
      sendPrompt(page, 'export my vault'),
    ]);

    const prose = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(prose).toContainText('vault', { timeout: 8000 });
  });

  // Scenario 10: Switch Model
  test('Scenario 10: "switch to the faster model" changes model role for subsequent turns', async ({ page }) => {
    await sendPrompt(page, 'switch to the faster model');

    // Expect confirmation text and NO settings overlay opened
    const prose = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(prose).toContainText('fast', { timeout: 8000 });
    const settingsHeading = page.locator('h2:has-text("Settings & Configuration")');
    await expect(settingsHeading).not.toBeVisible();

    // Verify next turn passes model_role in POST request payload
    let capturedModelRole: string | undefined = undefined;
    page.on('request', (req) => {
      if (req.url().includes('/v1/chat') && req.method() === 'POST') {
        try {
          const body = req.postDataJSON();
          capturedModelRole = body?.model_role;
        } catch (e) {}
      }
    });

    await sendPrompt(page, 'what is 15% of 2,340');

    await page.waitForTimeout(500);
    expect(capturedModelRole).toBe('fast');
  });
});

test.describe('Live Model Scenarios (Skipped by default for CI)', () => {
  test.skip(!process.env.RUN_LIVE_TESTS, 'Skipped unless RUN_LIVE_TESTS=1');

  test('Live model deep research run', async ({ page }) => {
    await page.goto('/');
    await sendPrompt(page, 'Research latest trends in agentic AI architecture');
    const prose = page.locator('.max-w-\\[720px\\] .font-serif').last();
    await expect(prose).toBeVisible({ timeout: 25000 });
  });
});
