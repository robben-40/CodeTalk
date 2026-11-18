import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

const topics = [
  ["general", "Umum / Live Coding CS"],
  ["data_structures", "Struktur Data"],
  ["algorithms", "Algoritma & Kompleksitas"],
  ["oop", "OOP"],
  ["databases", "Basis Data"],
  ["operating_systems", "Sistem Operasi"],
  ["computer_networks", "Jaringan Komputer"],
  ["web_backend", "Web & Backend"],
  ["software_engineering", "Rekayasa Perangkat Lunak"],
  ["machine_learning", "AI & Machine Learning"],
].map(([key, label]) => ({ key, label }));

const finalText = "Setiap node menyimpan data dan pointer ke node berikutnya.";
const lastText = `${finalText} Head menunjuk ke node pertama.`;
const markdown =
  "# Memahami linked list\n\nNode menyimpan data dan pointer.\n\n## Konsep utama\n\n- Head menunjuk node pertama.\n- Traversal membutuhkan O(n).\n\n```python\ncurrent = head\nwhile current is not None:\n    visit(current.data)\n    current = current.next\n```\n\n" +
  Array.from(
    { length: 12 },
    (_, index) =>
      `## Pembahasan ${index + 1}\n\nPenambahan di awal mengubah pointer tanpa menggeser seluruh elemen. Kompleksitas waktunya O(1).`,
  ).join("\n\n");

async function setup(page: Page, readyImmediately = true) {
  const frames: Buffer[] = [];
  const messages: ("audio" | "stop")[] = [];
  let socket: WebSocketRoute | undefined;
  let url = "";
  await page.route("**/topics", (route) =>
    route.fulfill({ json: { default_topic: "data_structures", topics } }),
  );
  await page.routeWebSocket(/\/ws\/stream\?/, (route) => {
    socket = route;
    url = route.url();
    route.onMessage((data) => {
      if (typeof data !== "string") {
        frames.push(Buffer.from(data));
        messages.push("audio");
      } else if (JSON.parse(data).type === "stop") {
        messages.push("stop");
        route.send(
          JSON.stringify({
            type: "transcript",
            final_text: "Head menunjuk ke node pertama.",
            committed_transcript: lastText,
            partial_text: "",
            window_start_sec: 1.2,
            latency_ms: 440,
            rtf: 0.28,
          }),
        );
        route.send(
          JSON.stringify({
            type: "stopped",
            reason: "stop",
            committed_transcript: lastText,
            summary: { steps: 2 },
          }),
        );
      }
    });
    if (readyImmediately)
      route.send(
        JSON.stringify({
          type: "ready",
          session_id: "test-session",
          sample_rate: 16000,
          topic: "data_structures",
        }),
      );
  });
  await page.addInitScript(() => {
    const device = navigator.mediaDevices;
    const original = device.getUserMedia.bind(device);
    const streams: MediaStream[] = [];
    Object.assign(window, { testStreams: streams });
    device.getUserMedia = async (constraints) => {
      const stream = await original(constraints);
      streams.push(stream);
      return stream;
    };
  });
  await page.goto("/");
  await expect(page.getByLabel("Mata kuliah", { exact: true })).toHaveValue(
    "data_structures",
  );
  return {
    frames,
    messages,
    get socket() {
      return socket!;
    },
    get url() {
      return url;
    },
    ready() {
      socket!.send(
        JSON.stringify({
          type: "ready",
          session_id: "test-session",
          sample_rate: 16000,
          topic: "data_structures",
        }),
      );
    },
    transcript() {
      socket!.send(JSON.stringify({ type: "status", state: "processing" }));
      socket!.send(
        JSON.stringify({
          type: "transcript",
          committed_transcript: finalText,
          final_text: finalText,
          partial_text: "Head menunjuk",
          window_start_sec: 0.5,
          latency_ms: 820,
          rtf: 0.42,
        }),
      );
    },
  };
}

test("streams only after ready, deduplicates final text, and flushes before stop", async ({
  page,
}) => {
  const backend = await setup(page, false);
  await page
    .getByLabel("Istilah tambahan", { exact: false })
    .fill("sentinel node, ListNode, sentinel node");
  await page.getByRole("button", { name: "Mulai rekam", exact: true }).click();
  await expect.poll(() => Boolean(backend.socket)).toBe(true);
  await page.waitForTimeout(250); // Explicitly verify the absence of audio before server readiness.
  expect(backend.frames).toHaveLength(0);
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { testStreams: MediaStream[] }).testStreams
          .length,
    ),
  ).toBe(0);
  expect(new URL(backend.url).searchParams.get("extra_terms")).toBe(
    "sentinel node,ListNode",
  );
  backend.ready();
  await expect(
    page.getByRole("button", { name: "Akhiri rekaman" }),
  ).toBeEnabled();
  await expect.poll(() => backend.frames.length).toBeGreaterThan(1);
  expect(backend.frames[0].byteLength).toBe(3200);
  backend.transcript();
  backend.transcript();
  await expect(
    page
      .getByRole("region", { name: "Isi transkrip", exact: true })
      .getByText(finalText, { exact: true }),
  ).toHaveCount(1);
  await expect(page.getByText("Sementara", { exact: true })).toBeVisible();
  await expect(page.getByText("820 ms", { exact: true })).toBeVisible();
  await expect(page.getByText("0.42", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Akhiri rekaman" }).click();
  await expect(
    page.getByRole("button", { name: "Sesi baru", exact: false }),
  ).toBeEnabled();
  await expect(page.getByText("Sementara", { exact: true })).toHaveCount(0);
  expect(backend.messages.at(-1)).toBe("stop");
  expect(
    backend.frames.every(
      (frame) =>
        frame.byteLength > 0 &&
        frame.byteLength <= 3200 &&
        frame.byteLength % 2 === 0,
    ),
  ).toBe(true);
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as unknown as { testStreams: MediaStream[] }).testStreams.every(
          (stream) =>
            stream.getTracks().every((track) => track.readyState === "ended"),
        ),
      ),
    )
    .toBe(true);
});

test("generates from final text, keeps panel actions fixed, exports and resets", async ({
  page,
}, testInfo) => {
  const backend = await setup(page);
  let body: { transcript: string; topic: string } | undefined;
  await page.route("**/api/notes", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ json: { markdown } });
  });
  await page.getByRole("button", { name: "Mulai rekam", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Akhiri rekaman" }),
  ).toBeEnabled();
  backend.transcript();
  await page.getByRole("button", { name: "Buat Smart Note" }).click();
  const notes = page.getByRole("region", {
    name: "Isi Smart Notes",
    exact: true,
  });
  await expect(
    notes.getByRole("heading", { name: "Memahami linked list", exact: true }),
  ).toBeVisible();
  expect(body).toEqual({ transcript: finalText, topic: "data_structures" });
  const generate = page.getByRole("button", {
    name: "Perbarui catatan",
    exact: true,
  });
  const before = await generate.boundingBox();
  await notes.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  expect((await generate.boundingBox())!.y).toBe(before!.y);
  await page.getByRole("button", { name: "Akhiri rekaman" }).click();
  await expect(
    page.getByRole("button", { name: "Sesi baru", exact: false }),
  ).toBeEnabled();
  await page.locator("summary").filter({ hasText: "Ekspor" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Transkrip .txt", exact: false })
    .click();
  expect((await downloadPromise).suggestedFilename()).toMatch(/\.txt$/);
  await page.locator("summary").filter({ hasText: "Ekspor" }).click();
  const metricsPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Metrik sesi .json", exact: false })
    .click();
  expect((await metricsPromise).suggestedFilename()).toMatch(/\.json$/);
  await page.evaluate(() => {
    window.print = () => {
      Object.assign(window, { printed: true });
    };
  });
  await page.locator("summary").filter({ hasText: "Ekspor" }).click();
  await page
    .getByRole("button", { name: "Smart Notes .pdf", exact: false })
    .click();
  expect(
    await page.evaluate(
      () => (window as unknown as { printed: boolean }).printed,
    ),
  ).toBe(true);
  await notes.evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.screenshot({ path: testInfo.outputPath("workspace.png") });
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".app-shell")).toBeHidden();
  await expect(page.locator(".print-notes")).toBeVisible();
  await expect(
    page
      .locator(".print-notes")
      .getByRole("heading", { name: "Pembahasan 12", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("print-preview.png"),
    fullPage: true,
  });
  await page.emulateMedia({ media: "screen" });
  await page.getByRole("button", { name: "Sesi baru", exact: false }).click();
  await expect(
    page.getByRole("heading", { name: "Konteks mata kuliah" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mulai rekam", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Buat Smart Note", exact: true }),
  ).toBeDisabled();
  await expect(
    page
      .getByRole("region", { name: "Isi transkrip", exact: true })
      .getByText(finalText),
  ).toHaveCount(0);
});

test("microphone denial cleans up the connection and exposes a retryable error", async ({
  page,
}) => {
  await setup(page);
  await page.evaluate(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      throw new DOMException("Denied", "NotAllowedError");
    };
  });
  await page.getByRole("button", { name: "Mulai rekam", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Akses mikrofon ditolak");
  await expect(
    page.getByRole("button", { name: "Sesi baru", exact: false }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Mulai rekam", exact: true }),
  ).toBeEnabled();
});

test("pending initialization can be cancelled without sending audio", async ({
  page,
}) => {
  const backend = await setup(page, false);
  await page.getByRole("button", { name: "Mulai rekam", exact: true }).click();
  await expect.poll(() => Boolean(backend.socket)).toBe(true);
  await page.getByRole("button", { name: "Batalkan", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Mulai rekam", exact: true }),
  ).toBeEnabled();
  expect(backend.frames).toHaveLength(0);
});

test("a microphone stream granted after cancellation is released immediately", async ({
  page,
}) => {
  const backend = await setup(page);
  await page.evaluate(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(
      navigator.mediaDevices,
    );
    navigator.mediaDevices.getUserMedia = (constraints) =>
      new Promise<MediaStream>((resolve, reject) => {
        Object.assign(window, {
          grantLateMicrophone: () =>
            original(constraints).then(resolve, reject),
        });
      });
  });
  await page.getByRole("button", { name: "Mulai rekam", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          typeof (window as unknown as { grantLateMicrophone?: unknown })
            .grantLateMicrophone,
      ),
    )
    .toBe("function");
  await page.getByRole("button", { name: "Batalkan", exact: true }).click();
  await page.evaluate(() =>
    (
      window as unknown as { grantLateMicrophone: () => Promise<void> }
    ).grantLateMicrophone(),
  );
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { testStreams: MediaStream[] }).testStreams
            .length,
      ),
    )
    .toBe(1);
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as unknown as { testStreams: MediaStream[] }).testStreams.every(
          (stream) =>
            stream.getTracks().every((track) => track.readyState === "ended"),
        ),
      ),
    )
    .toBe(true);
  await expect(
    page.getByRole("button", { name: "Mulai rekam", exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(backend.frames).toHaveLength(0);
});

test("disconnect preserves received text and releases the microphone", async ({
  page,
}) => {
  const backend = await setup(page);
  await page.getByRole("button", { name: "Mulai rekam", exact: true }).click();
  await expect.poll(() => backend.frames.length).toBeGreaterThan(0);
  backend.transcript();
  await expect(page.getByText(finalText, { exact: true })).toBeVisible();
  await backend.socket.close({ code: 1011, reason: "Test disconnect" });
  await expect(page.getByRole("alert")).toContainText("Koneksi terputus");
  await expect(page.getByText(finalText, { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Sesi baru", exact: false }),
  ).toBeEnabled();
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as unknown as { testStreams: MediaStream[] }).testStreams.every(
          (stream) =>
            stream.getTracks().every((track) => track.readyState === "ended"),
        ),
      ),
    )
    .toBe(true);
});

test("unavailable notes service reports the limitation without inventing notes", async ({
  page,
}) => {
  const backend = await setup(page);
  await page.route("**/api/notes", (route) =>
    route.fulfill({ status: 404, json: { detail: "Not Found" } }),
  );
  await page.getByRole("button", { name: "Mulai rekam", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Akhiri rekaman" }),
  ).toBeEnabled();
  backend.transcript();
  await page.getByRole("button", { name: "Buat Smart Note" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Layanan Smart Notes belum tersedia",
  );
  await expect(page.getByText(finalText, { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Memahami linked list", exact: true }),
  ).toHaveCount(0);
});

test("320px layout keeps both context fields aligned and supports panel tabs", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await setup(page);
  const course = await page
    .getByLabel("Mata kuliah", { exact: true })
    .boundingBox();
  const terms = await page
    .getByLabel("Istilah tambahan", { exact: false })
    .boundingBox();
  expect(course!.y).toBe(terms!.y);
  expect(terms!.x).toBeGreaterThan(course!.x);
  await expect(
    page.getByRole("button", { name: "Mulai rekam", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Smart Notes", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Buat Smart Note", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Transkrip", exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("mobile.png") });
});
