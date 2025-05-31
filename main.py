from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse
from pydantic import HttpUrl
from playwright.async_api import async_playwright
from cachetools import TTLCache
from contextlib import asynccontextmanager
import asyncio
from typing import Optional

# Cache with 1 hour TTL and max 1000 entries
cache = TTLCache(maxsize=1000, ttl=3600)

# Concurrency control (max 50 concurrent requests)
semaphore = asyncio.Semaphore(50)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch browser at startup
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage'
            ]
        )
        app.state.browser = browser  # Store browser on app state
        app.state.playwright = playwright
        
        yield {
            "playwright": playwright,
            "browser": browser
        }
    finally:
        # Cleanup resources
        if hasattr(app.state, 'browser'):
            await app.state.browser.close()
        if hasattr(app.state, 'playwright'):
            await app.state.playwright.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/scrape", response_class=PlainTextResponse)
async def scrape_url(
    request: Request,
    url: str = Query(..., description="URL to scrape")
):
    # Check cache first
    # Validate URL format
    if not url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    if url in cache:
        return cache[url]

    browser = request.app.state.browser

    async with semaphore:  # Concurrency control
        try:
            browser = request.app.state.browser
            page = await browser.new_page()
            
            try:
                # Navigate with timeout
                await page.goto(url, timeout=60000)
                content = await page.content()

                # Store in cache
                cache[url] = content
                return content
            except Exception as e:
                await page.close()
                raise HTTPException(status_code=500, detail=f"Page navigation failed: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Browser operation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)