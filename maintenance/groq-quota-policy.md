# Groq quota protection

Production keeps the source-grounded generator and separate editorial pass. No
fallback model or canned text is added.

* Every HTTP attempt, including connection errors, JSON repairs and retries,
  consumes all active request budgets. An item gets at most six attempts by
  default. A three-video run gets at most eighteen total; a six-video run gets
  thirty-six. `GROQ_MAX_REQUESTS_PER_ITEM` and `GROQ_MAX_REQUESTS_PER_RUN` can lower
  these allowances. Quiz bulk requests scale the item allowance with the requested
  question count. These are process/run limits, not an organization-wide daily
  token quota. Other repositories and simultaneous runs share the provider quota.
* Each individual API operation has at most three transport/schema attempts.
  Any HTTP 429 ends the run immediately. Production saves the provider cooldown
  for the next scheduled run. The daily request reset is used only if daily
  requests are exhausted. The existing four repository time slots are retained.
* A truncated response already at the completion cap is rejected without sending
  the identical request again. Corrupt diagnostic JSON is logged and ignored.
* Saved candidates are visited once per run. Provider failures retain accepted
  upload IDs. Quiz/editor evidence and fact-video quotes must occur in the bound
  real source; this check supports editorial review and does not prove every
  narrated claim true.

Run `python maintenance/offline_tests.py` from the application directory to run
the regression suite with fake credentials and external network blocked. The test runner uses no repository secrets and does not generate or upload videos. Passing these tests does not establish live model
content quality or successful YouTube delivery.
