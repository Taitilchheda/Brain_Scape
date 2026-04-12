const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

async function run() {
    const outDir = path.resolve('data/outputs/demo');
    fs.mkdirSync(outDir, { recursive: true });

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        viewport: { width: 1280, height: 720 },
        recordVideo: {
            dir: outDir,
            size: { width: 1280, height: 720 },
        },
    });

    const page = await context.newPage();
    await page.goto('http://127.0.0.1:8000/', { waitUntil: 'networkidle' });

    await page.waitForTimeout(1000);
    await page.click('#btn-login');
    await page.waitForTimeout(1000);

    await page.click('#btn-demo');
    await page.waitForSelector('#region-list .region-item', { timeout: 20000 });
    await page.waitForTimeout(1500);

    await page.fill('#qa-input', 'What is the main finding in this demo scan?');
    await page.keyboard.press('Enter');
    await page.waitForSelector('#qa-response', { state: 'visible', timeout: 20000 });
    await page.waitForTimeout(2500);

    const canvas = page.locator('#brain-canvas');
    const box = await canvas.boundingBox();
    if (box) {
        const x = box.x + box.width / 2;
        const y = box.y + box.height / 2;
        await page.mouse.move(x, y);
        await page.mouse.down();
        await page.mouse.move(x + 220, y + 10, { steps: 30 });
        await page.mouse.move(x - 120, y - 20, { steps: 20 });
        await page.mouse.up();
    }

    await page.waitForTimeout(1500);
    await page.click('#btn-export-report');
    await page.waitForTimeout(1500);

    for (const p of context.pages()) {
        if (p !== page) {
            await p.close();
        }
    }

    const video = page.video();
    await page.close();
    const rawVideoPath = await video.path();

    await context.close();
    await browser.close();

    const finalVideoPath = path.join(outDir, 'brainscape-dom-demo.webm');
    fs.copyFileSync(rawVideoPath, finalVideoPath);

    console.log(`DOM demo video saved: ${finalVideoPath}`);
}

run().catch((err) => {
    console.error('Failed to record DOM demo video:', err);
    process.exit(1);
});
