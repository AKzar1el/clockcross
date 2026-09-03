import json
import subprocess
from pathlib import Path


TRIGGER = Path("deploy/cloudflare-competition-trigger")
WRANGLER = TRIGGER / "wrangler.jsonc"
WORKER = TRIGGER / "src" / "index.mjs"


def test_cloudflare_competition_trigger_declares_sep4_1330_utc_cron_without_secrets():
    config_text = WRANGLER.read_text(encoding="utf-8")
    config = json.loads(config_text)

    assert config["name"] == "clockcross-competition-trigger"
    assert config["main"] == "src/index.mjs"
    assert config["triggers"]["crons"] == ["30 13 4 9 *"]
    assert "CLOCKCROSS_GITHUB_TOKEN" not in config_text
    assert "github_pat_" not in config_text
    assert "ghp_" not in config_text


def test_cloudflare_competition_trigger_dispatches_only_exact_sep4_event():
    script = r'''
import worker from "./deploy/cloudflare-competition-trigger/src/index.mjs";

const calls = [];
globalThis.fetch = async (url, init) => {
  calls.push({url, init});
  return {ok: true, status: 200};
};

const env = {CLOCKCROSS_GITHUB_TOKEN: "test-token-not-a-real-secret"};
const makeController = (iso, cron = "30 13 4 9 *") => ({
  cron,
  scheduledTime: Date.parse(iso),
  noRetryCalled: false,
  noRetry() { this.noRetryCalled = true; },
});

const wrongDate = makeController("2027-09-04T13:30:00Z");
await worker.scheduled(wrongDate, env, {});
if (!wrongDate.noRetryCalled) throw new Error("wrong-date invocation did not disable retry");
if (calls.length !== 0) throw new Error("wrong-date invocation dispatched");

const wrongCron = makeController("2026-09-04T13:30:00Z", "35 13 4 9 *");
await worker.scheduled(wrongCron, env, {});
if (!wrongCron.noRetryCalled) throw new Error("wrong-cron invocation did not disable retry");
if (calls.length !== 0) throw new Error("wrong-cron invocation dispatched");

const target = makeController("2026-09-04T13:30:00Z");
await worker.scheduled(target, env, {});
if (!target.noRetryCalled) throw new Error("target invocation did not disable retry");
if (calls.length !== 1) throw new Error(`expected one dispatch, got ${calls.length}`);

const call = calls[0];
if (call.url !== "https://api.github.com/repos/AKzar1el/clockcross/actions/workflows/competition-runtime.yml/dispatches") {
  throw new Error(`unexpected dispatch URL: ${call.url}`);
}
if (call.init.method !== "POST") throw new Error("dispatch was not POST");
if (call.init.headers.Authorization !== "Bearer test-token-not-a-real-secret") {
  throw new Error("dispatch did not use bearer auth from Worker secret");
}
if (call.init.headers["X-GitHub-Api-Version"] !== "2026-03-10") {
  throw new Error("dispatch did not pin current GitHub API version");
}

const body = JSON.parse(call.init.body);
if (body.ref !== "main") throw new Error("dispatch did not target main");
if (body.inputs?.session_date !== "2026-09-04") {
  throw new Error("dispatch did not pin Sep 4 session date");
}
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_cloudflare_competition_trigger_fails_closed_without_token_or_on_github_error():
    script = r'''
import worker from "./deploy/cloudflare-competition-trigger/src/index.mjs";

const makeController = () => ({
  cron: "30 13 4 9 *",
  scheduledTime: Date.parse("2026-09-04T13:30:00Z"),
  noRetry() {},
});

let missingTokenFailed = false;
try {
  await worker.scheduled(makeController(), {}, {});
} catch (error) {
  missingTokenFailed = String(error.message).includes("missing GitHub dispatch token");
}
if (!missingTokenFailed) throw new Error("missing token did not fail closed");

globalThis.fetch = async () => ({ok: false, status: 503});
let githubFailureFailed = false;
try {
  await worker.scheduled(
    makeController(),
    {CLOCKCROSS_GITHUB_TOKEN: "test-token-not-a-real-secret"},
    {},
  );
} catch (error) {
  githubFailureFailed = String(error.message).includes("status 503");
}
if (!githubFailureFailed) throw new Error("GitHub failure did not fail closed");
'''
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
