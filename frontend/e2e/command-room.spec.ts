import { expect, test } from './fixtures/localhostOnly';

test('Command Room loads from localhost:3000 only', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveURL('http://localhost:3000/');
  await expect(page.getByRole('heading', { name: 'Production Command' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Local workspace');
});

test('protected studio navigation redirects unauthenticated users to login', async ({ page }) => {
  await page.goto('/');

  await page.getByRole('link', { name: /Productions/ }).click();
  await expect(page).toHaveURL('http://localhost:3000/login');
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();

  await page.goto('/');
  await page.getByRole('link', { name: /Generated Media/ }).click();
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
