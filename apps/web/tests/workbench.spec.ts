import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("matched explorer fixture, keyboard controls and accessible layout", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("call-price")).toHaveText("10.4506");
  await page.getByLabel("Greek measure").selectOption("gamma");
  await page.getByRole("slider", { name: "Spot slider" }).press("ArrowRight");
  await expect(page.getByRole("spinbutton", { name: /Spot/ })).toHaveValue(
    "101",
  );
  await expect(page.getByTestId("call-price")).not.toHaveText("10.4506");
  const audit = await new AxeBuilder({ page }).analyze();
  expect(audit.violations).toEqual([]);
  await page.screenshot({
    path: "../../artifacts/explorer-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      page
        .locator(".recharts-surface")
        .evaluateAll((nodes) =>
          nodes.every((n) => n.getBoundingClientRect().width < 390),
        ),
    )
    .toBeTruthy();
  await page.screenshot({
    path: "../../artifacts/explorer-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("stress residual, paid integer hedges, saved assumptions and causal replay", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("call-price")).toHaveText("10.4506");
  await page.getByRole("tab", { name: "Portfolio & scenarios" }).click();
  await expect(page.getByTestId("full-change")).toContainText("USD");
  await expect(page.getByTestId("residual")).not.toContainText("0.00 USD");
  await page.screenshot({
    path: "../../artifacts/scenarios-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Hedge comparison" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Scenario CVaR · actual additional trades",
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Save comparison", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Saved run ID" }),
  ).not.toHaveValue("");
  await page
    .getByRole("spinbutton", { name: /Round-trip cost budget/ })
    .fill("0");
  await page.getByRole("button", { name: "Load saved comparison" }).click();
  await expect(
    page.getByText("Saved snapshot · calculations use the original run"),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/hedges-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Replay & evaluation" }).click();
  await page.getByRole("button", { name: "Run causal replay" }).click();
  await expect(
    page.getByRole("spinbutton", { name: "Replay node", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("spinbutton", { name: "Replay node", exact: true })
    .fill("64");
  await expect(
    page.getByText("Requested shares", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Replay run ID")).not.toHaveValue("");
  await page.getByLabel("Replay generator").selectOption("matched");
  await page.getByRole("button", { name: "Load saved replay" }).click();
  await expect(
    page.getByText("Saved run: jump-delay", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("spinbutton", { name: "Replay node", exact: true })
    .fill("64");
  await page.getByLabel("Timeline companion").selectOption("iv");
  await expect(
    page.getByRole("term").filter({ hasText: "Assigned IV annual %" }),
  ).toBeVisible();
  await page
    .getByText("Financed error distribution · independent paths", {
      exact: true,
    })
    .click();
  await page.getByText("Full cash / fill audit", { exact: true }).click();
  await page.screenshot({
    path: "../../artifacts/replay-desktop.png",
    fullPage: true,
  });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      page
        .locator(".recharts-surface")
        .evaluateAll((nodes) =>
          nodes.every((n) => n.getBoundingClientRect().width < 390),
        ),
    )
    .toBeTruthy();
  await page.screenshot({
    path: "../../artifacts/replay-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});

test("obsolete curve responses and backend errors cannot replace latest results", async ({
  page,
}) => {
  await page.route("**/api/curves", async (route) => {
    const c = route.request().postDataJSON();
    const response = await route.fetch();
    if (c.market.spot === 110) await new Promise((r) => setTimeout(r, 600));
    if (c.market.spot === 120) {
      await route.fulfill({
        status: 422,
        json: { detail: "Injected numerical failure" },
      });
      return;
    }
    await route.fulfill({ response });
  });
  await page.goto("/");
  await expect(page.getByTestId("call-price")).toHaveText("10.4506");
  await page.getByRole("spinbutton", { name: /Spot/ }).fill("110");
  await page.waitForRequest(
    (r) =>
      r.url().includes("/api/curves") && r.postDataJSON().market.spot === 110,
  );
  await page.getByRole("spinbutton", { name: /Spot/ }).fill("105");
  await expect(page.getByTestId("call-price")).toHaveText("13.8579");
  await page.waitForTimeout(700);
  await expect(page.getByTestId("call-price")).toHaveText("13.8579");
  await page.getByRole("spinbutton", { name: /Spot/ }).fill("120");
  await expect(page.getByRole("alert")).toContainText(
    "Injected numerical failure",
  );
  await page.getByRole("spinbutton", { name: /Spot/ }).fill("100");
  await expect(page.getByTestId("call-price")).toHaveText("10.4506");
});

test("signed Greek exposure, invalid field recovery and protected model boundary", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("call-price")).toHaveText("10.4506");
  await page.getByLabel("Exposure basis").selectOption("signed-contracts");
  await expect(page.getByTestId("call-price")).toHaveText("-1,045.0584");
  await page.getByRole("spinbutton", { name: /Spot/, exact: true }).fill("-1");
  await expect(page.getByRole("alert")).toContainText("last valid value");
  await page.getByRole("spinbutton", { name: /Spot/, exact: true }).fill("100");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByRole("tab", { name: "Model benchmark" }).click();
  await expect(page.getByTestId("active-engine")).toHaveText(
    "Active engine: reference",
  );
  await page.getByRole("button", { name: "Inspect exercise boundary" }).click();
  await expect(
    page.getByRole("spinbutton", { name: /Probe maturity/ }),
  ).toHaveValue("7");
  await expect(
    page.getByText("derivative-aware: rejected", { exact: false }),
  ).toBeVisible();
  await page.getByLabel("Evaluation region").selectOption("ood");
  await page.getByText("Budget, convergence and fair timings").click();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../artifacts/benchmark-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      page
        .locator(".recharts-surface")
        .evaluateAll((nodes) =>
          nodes.every((n) => n.getBoundingClientRect().width < 390),
        ),
    )
    .toBeTruthy();
  await page.screenshot({
    path: "../../artifacts/benchmark-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("all surfaces pass keyboard and accessibility review", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("call-price")).toHaveText("10.4506");
  await page.getByRole("tab", { name: "Greek explorer" }).focus();
  await page.getByRole("tab", { name: "Greek explorer" }).press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Portfolio & scenarios" }),
  ).toBeFocused();
  await page.getByRole("tab", { name: "Portfolio & scenarios" }).press("Enter");
  await expect(page.getByTestId("full-change")).toBeVisible();
  for (const name of [
    "Portfolio & scenarios",
    "Hedge comparison",
    "Replay & evaluation",
    "Model benchmark",
  ]) {
    await page.getByRole("tab", { name }).click();
    await expect(
      page.getByText("Calculating with shared numerical service…"),
    ).toHaveCount(0);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(async () =>
        page
          .locator(".recharts-surface")
          .evaluateAll((nodes) =>
            nodes.every((n) => n.getBoundingClientRect().width < 390),
          ),
      )
      .toBeTruthy();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
});

test("model prices, Monte Carlo uncertainty and linked paid model replay", async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByTestId("call-price")).toHaveText("10.4506");
  await page.getByRole("tab", { name: "Model benchmark" }).click();
  await page
    .getByRole("button", { name: "Pricing models & Monte Carlo" })
    .click();
  await expect(page.getByTestId("bsm-model-price")).toHaveText("10.450584");
  await expect(page.getByTestId("merton-model-price")).toHaveText("10.450584");
  await expect(page.getByTestId("heston-model-price")).toHaveText("10.450584");
  await page.getByLabel("Model curve measure").selectOption("gamma");
  await page
    .getByText("Full repricing versus local spot Greeks", { exact: true })
    .click();
  await page.getByLabel("MC paths", { exact: true }).selectOption("4096");
  await page
    .getByRole("button", { name: "Run Monte Carlo comparison" })
    .click();
  await expect(page.getByTestId("mc-saved")).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("region", { name: "Monte Carlo numerical error" }),
  ).toContainText("95% sampling CI");
  await page.getByLabel("Match initial premium at selected contract").uncheck();
  await expect(page.getByTestId("merton-model-price")).toHaveText("11.118030");
  await page.getByRole("button", { name: "Load saved MC run" }).click();
  await expect(page.getByTestId("mc-saved")).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../artifacts/model-comparison-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page
        .locator(".recharts-surface")
        .evaluateAll((nodes) =>
          nodes.every((n) => n.getBoundingClientRect().width < 390),
        ),
    )
    .toBeTruthy();
  await page.screenshot({
    path: "../../artifacts/model-comparison-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("spinbutton", { name: /Jump intensity/, exact: true })
    .fill("0.3");
  await page.getByRole("button", { name: "Compare paid model hedges" }).click();
  await expect(page.getByTestId("linked-model-config")).toContainText(
    "lambda 0.3",
  );
  await expect(
    page.getByRole("heading", {
      name: "Does a different model improve the paid hedge?",
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Run model hedge comparison" })
    .click();
  await expect(page.getByTestId("model-replay-saved")).toBeVisible({
    timeout: 30000,
  });
  await page
    .getByRole("spinbutton", { name: "Model replay node", exact: true })
    .fill("64");
  await expect(
    page.getByRole("term").filter({ hasText: "Observed variance" }),
  ).toBeVisible();
  await page.getByLabel("Model replay generator").selectOption("merton");
  await page.getByRole("button", { name: "Load saved model replay" }).click();
  await expect(page.getByTestId("model-replay-saved")).toContainText("heston");
  await page.getByLabel("Model timeline companion").selectOption("variance");
  const spotTickLabels = page
    .locator(".recharts-yAxis-tick-labels")
    .first()
    .locator(".recharts-cartesian-axis-tick-value");
  await expect(spotTickLabels.first()).toBeVisible();
  const spotTicks = await spotTickLabels.allTextContents();
  expect(spotTicks.length).toBeGreaterThan(1);
  expect(spotTicks.every((tick) => /^\d{1,3}$/.test(tick))).toBeTruthy();
  await page.getByText("Full model replay cash audit", { exact: true }).click();
  await page
    .getByRole("button", { name: "Load protected model evaluation" })
    .click();
  await expect(page.getByTestId("protected-model-evidence")).toContainText(
    "387,072",
  );
  await page.getByLabel("Model replay generator").selectOption("heston");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({
    path: "../../artifacts/model-replay-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page
        .locator(".recharts-surface")
        .evaluateAll((nodes) =>
          nodes.every((n) => n.getBoundingClientRect().width < 390),
        ),
    )
    .toBeTruthy();
  await page.screenshot({
    path: "../../artifacts/model-replay-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(errors).toEqual([]);
});

test("model comparison rejects invalid matching and ignores obsolete responses", async ({
  page,
}) => {
  await page.route("**/api/models/compare", async (route) => {
    const config = route.request().postDataJSON();
    const response = await route.fetch();
    if (config.point.parameters.intensity === 0.5)
      await new Promise((r) => setTimeout(r, 600));
    if (config.point.parameters.intensity === 0.6) {
      await route.fulfill({
        status: 422,
        json: { detail: "Injected model integration failure" },
      });
      return;
    }
    await route.fulfill({ response });
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "Model benchmark" }).click();
  await page
    .getByRole("button", { name: "Pricing models & Monte Carlo" })
    .click();
  await expect(page.getByTestId("bsm-model-price")).toHaveText("10.450584");
  await page
    .getByRole("spinbutton", { name: /Jump intensity/, exact: true })
    .fill("0.5");
  await page.waitForRequest(
    (r) =>
      r.url().includes("/api/models/compare") &&
      r.postDataJSON().point.parameters.intensity === 0.5,
  );
  await page
    .getByRole("spinbutton", { name: /Jump intensity/, exact: true })
    .fill("0.4");
  await expect(page.getByTestId("merton-model-price")).toHaveText("10.450584");
  await page.waitForTimeout(700);
  await expect(page.getByTestId("model-match-basis")).toContainText(
    "One-point",
  );
  await page
    .getByRole("spinbutton", { name: /Jump intensity/, exact: true })
    .fill("0.6");
  await expect(page.getByRole("alert")).toContainText(
    "Injected model integration failure",
  );
  await page
    .getByRole("spinbutton", { name: /Jump intensity/, exact: true })
    .fill("0.4");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page
    .getByRole("spinbutton", { name: /Jump intensity/, exact: true })
    .fill("-1");
  await expect(page.getByRole("alert")).toContainText("last valid value");
  await page
    .getByRole("spinbutton", { name: /Jump intensity/, exact: true })
    .fill("0.4");
  await expect(page.getByRole("alert")).toHaveCount(0);
});
