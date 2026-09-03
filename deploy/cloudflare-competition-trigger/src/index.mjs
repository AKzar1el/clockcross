const TARGET_DATE = "2026-09-04";
const TARGET_CRON = "30 13 4 9 *";
const DISPATCH_URL =
  "https://api.github.com/repos/AKzar1el/clockcross/actions/workflows/competition-runtime.yml/dispatches";

async function dispatchCompetition(env) {
  if (!env.CLOCKCROSS_GITHUB_TOKEN) {
    throw new Error("missing GitHub dispatch token");
  }

  const response = await fetch(DISPATCH_URL, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.CLOCKCROSS_GITHUB_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "clockcross-cloudflare-competition-trigger",
      "X-GitHub-Api-Version": "2026-03-10",
    },
    body: JSON.stringify({
      ref: "main",
      inputs: {
        session_date: TARGET_DATE,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`GitHub workflow dispatch failed with status ${response.status}`);
  }
}

export default {
  async scheduled(controller, env) {
    // GitHub's 09:35 and 09:45 ET schedules remain the retry/fallback plane.
    // Avoid an ambiguous duplicate dispatch if GitHub accepted this request but
    // Cloudflare did not observe the response.
    controller.noRetry();

    if (controller.cron !== TARGET_CRON) {
      return;
    }

    const scheduledDate = new Date(controller.scheduledTime).toISOString().slice(0, 10);
    if (scheduledDate !== TARGET_DATE) {
      return;
    }

    await dispatchCompetition(env);
  },
};
