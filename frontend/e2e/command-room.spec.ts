import { expect, test } from './fixtures/localhostOnly';

const lowerWorkspaceStorageKey = 'omniposter.commandRoom.lowerWorkspaceOpen';

test.beforeEach(async ({ page }) => {
  await page.addInitScript((key) => window.localStorage.removeItem(key), lowerWorkspaceStorageKey);
});

test('Command Room loads from localhost:3000 only', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveURL('http://localhost:3000/');
  await expect(page.getByRole('heading', { name: 'Start with the next video worth rendering.' })).toBeVisible();
  await expect(page.getByLabel('Design-review states').getByText('First run')).toBeVisible();
  const activeProductions = page.locator('#active-productions');
  await expect(activeProductions.getByRole('heading', { name: 'Active productions' })).toBeVisible();
  await expect(activeProductions.getByText('Nothing here yet — your first production appears once you generate a script.')).toBeVisible();
  await expect(activeProductions.locator('.chip', { hasText: 'Empty' })).toBeVisible();
  await expect(activeProductions.locator('.cr-empty-productions').getByText('No productions yet.')).toBeVisible();
});

test('protected studio navigation redirects unauthenticated users to login', async ({ page }) => {
  await page.goto('/');

  await page.locator('.op-nav').getByRole('link', { name: /Productions/ }).click();
  await expect(page).toHaveURL('http://localhost:3000/login');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();

  await page.goto('/');
  await page.locator('.op-nav').getByRole('link', { name: /Generated Media/ }).click();
  await expect(page).toHaveURL('http://localhost:3000/login');
  await expect(page.getByText('Sign in to manage projects, voice presets, renders, and publishing workflows.')).toBeVisible();
});

test('direct studio deep links render the React app instead of API JSON', async ({ page }) => {
  await page.goto('/projects');

  await expect(page).toHaveURL('http://localhost:3000/login');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await expect(page.locator('body')).not.toHaveText('{"items":[]}');

  await page.goto('/generated-media');
  await expect(page).toHaveURL('http://localhost:3000/login');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
});

test('command room reference shell keeps primary actions interactive', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Start with the next video worth rendering.' })).toBeVisible();
  await expect(page.locator('.shell.op-shell')).toBeVisible();
  await expect(page.locator('.sidebar.op-sidebar')).toBeVisible();
  await expect(page.locator('.topbar')).toBeVisible();

  await page.getByRole('button', { name: /Start First Production/ }).first().click();
  await expect(page).toHaveURL('http://localhost:3000/login');
});

test('command room lower workspace expands and collapses', async ({ page }) => {
  await page.goto('/');

  const drawer = page.locator('.cr-lower-workspace');
  await expect(drawer).not.toHaveAttribute('open', '');
  await page.getByText(/Lower workspace/).click();
  await expect(drawer).toHaveAttribute('open', '');
  await expect(page.getByText('Queue summary', { exact: true })).toBeVisible();
  await page.getByText(/Lower workspace/).click();
  await expect(drawer).not.toHaveAttribute('open', '');
});

test('command room keeps sticky runtime bar and no horizontal overflow', async ({ page }) => {
  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1024, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Start with the next video worth rendering.' })).toBeVisible();

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      bodyScrollWidth: document.body.scrollWidth,
      bodyClientWidth: document.body.clientWidth,
    }));
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
    expect(overflow.bodyScrollWidth).toBeLessThanOrEqual(overflow.bodyClientWidth + 1);

    await page.evaluate(() => window.scrollTo(0, 520));
    await expect(page.locator('.topbar')).toBeInViewport();
    const topbar = await page.locator('.topbar').boundingBox();
    expect(topbar?.y ?? 999).toBeLessThanOrEqual(8);
    expect(topbar?.y ?? -999).toBeGreaterThanOrEqual(0);
  }
});

test('command room uses compact icon rail on narrow screens', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 768 });
  await page.goto('/');

  const sidebarBox = await page.locator('.sidebar.op-sidebar').boundingBox();
  expect(sidebarBox?.width ?? 999).toBeLessThanOrEqual(80);
  await expect(page.locator('.op-nav').getByRole('link', { name: 'Command Room' })).toBeVisible();
});

test('command room brief fields stay horizontal on laptop width', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto('/');

  const fieldRows = await page.evaluate(() =>
    ['brief-format', 'brief-duration', 'brief-tone', 'brief-platform'].map((id) => {
      const rect = document.getElementById(id)?.getBoundingClientRect();
      return rect ? { x: rect.x, y: rect.y, width: rect.width } : null;
    })
  );

  expect(fieldRows.every(Boolean)).toBe(true);
  const [format, duration, tone, platform] = fieldRows as Array<{ x: number; y: number; width: number }>;
  expect(Math.max(format.y, duration.y, tone.y, platform.y) - Math.min(format.y, duration.y, tone.y, platform.y)).toBeLessThanOrEqual(8);
  expect(format.x).toBeLessThan(duration.x);
  expect(duration.x).toBeLessThan(tone.x);
  expect(tone.x).toBeLessThan(platform.x);
  expect(Math.min(format.width, duration.width, tone.width, platform.width)).toBeGreaterThan(110);
});

test('command room expanded lower workspace cards stay horizontal on laptop width', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto('/');

  await page.getByText(/Lower workspace/).click();
  await expect(page.getByText('Queue summary', { exact: true })).toBeVisible();

  const cards = await page.locator('.cr-lower-card').evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width };
    })
  );

  expect(cards).toHaveLength(3);
  expect(Math.max(...cards.map((card) => card.y)) - Math.min(...cards.map((card) => card.y))).toBeLessThanOrEqual(8);
  expect(cards[0].x).toBeLessThan(cards[1].x);
  expect(cards[1].x).toBeLessThan(cards[2].x);
  expect(Math.min(...cards.map((card) => card.width))).toBeGreaterThan(190);
});

test('command room preset cards contain chips and actions without overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/');

  await expect(page.locator('.cr-preset')).toHaveCount(4);
  const overflow = await page.locator('.cr-preset').evaluateAll((cards) =>
    cards.map((card) => {
      const cardRect = card.getBoundingClientRect();
      return Array.from(card.querySelectorAll('.chip, .btn, .cr-preset-struct')).filter((child) => {
        const rect = child.getBoundingClientRect();
        return rect.left < cardRect.left - 1 || rect.right > cardRect.right + 1;
      }).length;
    })
  );

  expect(overflow).toEqual([0, 0, 0, 0]);
});
